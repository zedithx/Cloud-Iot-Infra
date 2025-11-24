from dataclasses import dataclass

from aws_cdk import Duration, aws_events as events, aws_events_targets as targets, aws_iam, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources
from infra.stacks.notifications import NotificationResources


@dataclass
class SchedulingResources:
    capture_lambda: lambda_.Function
    hourly_rule: events.Rule
    metrics_evaluator_lambda: lambda_.Function
    metrics_rule: events.Rule


class SchedulingConstruct(Construct):
    """EventBridge scheduler and supporting Lambda for periodic capture jobs."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        notifications: NotificationResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            data_plane=data_plane,
            notifications=notifications,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        notifications: NotificationResources,
    ) -> SchedulingResources:
        capture_lambda = lambda_.Function(
            self,
            "CaptureSchedulerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/capture_scheduler"),
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "DYNAMO_TABLE_NAME": data_plane.telemetry_table.table_name,
                "RAW_BUCKET_NAME": data_plane.raw_images_bucket.bucket_name,
                "PHOTO_PREFIX": "photos",
                "PRESIGNED_URL_EXPIRY": "3600",  # 1 hour
            },
        )

        # Grant DynamoDB read access to list device IDs
        data_plane.telemetry_table.grant_read_data(capture_lambda)

        # Grant S3 permissions to generate presigned URLs
        data_plane.raw_images_bucket.grant_put(capture_lambda)

        # Grant IoT Core publish permissions for leaf/commands/*/photo topics
        account = app_context.env.account or "*"
        region = app_context.env.region or "*"
        capture_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=["iot:Publish"],
                resources=[
                    f"arn:aws:iot:{region}:{account}:topic/leaf/commands/*/photo",
                ],
            )
        )

        hourly_rule = events.Rule(
            self,
            "HourlyCaptureRule",
            schedule=events.Schedule.cron(minute="0"),
            targets=[targets.LambdaFunction(capture_lambda)],
            description="Trigger hourly placeholder capture job.",
        )

        metrics_lambda = lambda_.Function(
            self,
            "MetricsEvaluatorFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/metrics_evaluator"),
            timeout=Duration.seconds(60),
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "DYNAMO_TABLE_NAME": data_plane.telemetry_table.table_name,
                "SNS_TOPIC_ARN": notifications.alert_topic.topic_arn,
                "DEFAULT_THRESHOLD": str(app_context.config.alert_threshold),
                "ENV_WINDOW_MINUTES": "30",
            },
        )

        data_plane.telemetry_table.grant_read_data(metrics_lambda)
        notifications.alert_topic.grant_publish(metrics_lambda)

        metrics_rule = events.Rule(
            self,
            "MetricsEvaluationRule",
            schedule=events.Schedule.rate(Duration.minutes(5)),
            targets=[targets.LambdaFunction(metrics_lambda)],
            description="Evaluate device metrics and trigger alerts when averages exceed thresholds.",
        )

        return SchedulingResources(
            capture_lambda=capture_lambda,
            hourly_rule=hourly_rule,
            metrics_evaluator_lambda=metrics_lambda,
            metrics_rule=metrics_rule,
        )

