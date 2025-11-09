from dataclasses import dataclass

from aws_cdk import Duration, aws_events as events, aws_events_targets as targets, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources


@dataclass
class SchedulingResources:
    capture_lambda: lambda_.Function
    hourly_rule: events.Rule


class SchedulingConstruct(Construct):
    """EventBridge scheduler and supporting Lambda for periodic capture jobs."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            data_plane=data_plane,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
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
                "RAW_BUCKET_NAME": data_plane.raw_images_bucket.bucket_name,
                "CAPTURE_PREFIX": f"{app_context.stage}/scheduled",
            },
        )

        data_plane.raw_images_bucket.grant_put(capture_lambda)

        hourly_rule = events.Rule(
            self,
            "HourlyCaptureRule",
            schedule=events.Schedule.cron(minute="0"),
            targets=[targets.LambdaFunction(capture_lambda)],
            description="Trigger hourly placeholder capture job.",
        )

        return SchedulingResources(
            capture_lambda=capture_lambda,
            hourly_rule=hourly_rule,
        )

