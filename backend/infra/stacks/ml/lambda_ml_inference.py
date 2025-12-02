from dataclasses import dataclass

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Size,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
)
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources


@dataclass
class MlInferenceResources:
    batch_launcher_lambda: lambda_.Function
    results_processor_lambda: lambda_.Function
    results_bucket: s3.Bucket
    model_artifact_bucket: s3.Bucket
    batch_schedule: events.Rule


class LambdaMlInferenceConstruct(Construct):
    """Sets up Lambda batch transform infrastructure and schedules periodic jobs."""

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
    ) -> MlInferenceResources:
        batch_results_bucket = s3.Bucket(
            self,
            "BatchResultsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            auto_delete_objects=app_context.stage != "prod",
            removal_policy=(
                RemovalPolicy.RETAIN if app_context.stage == "prod" else RemovalPolicy.DESTROY
            ),
        )

        model_bucket = s3.Bucket(
            self,
            "ModelArtifactBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            auto_delete_objects=app_context.stage != "prod",
            removal_policy=(
                RemovalPolicy.RETAIN if app_context.stage == "prod" else RemovalPolicy.DESTROY
            ),
        )

        batch_inference = lambda_.DockerImageFunction(
            self,
            "BatchInferenceLambda",
            code=lambda_.DockerImageCode.from_image_asset(
                directory="runtime/lambdas/batch_inference"
            ),
            timeout=Duration.minutes(10),
            memory_size=2048,
            ephemeral_storage_size=Size.gibibytes(4),
            environment={
                "RAW_BUCKET": data_plane.raw_images_bucket.bucket_name,
                "BATCH_RESULTS_BUCKET": batch_results_bucket.bucket_name,
                "STAGE": app_context.stage,
                "MODEL_S3_URI": app_context.config.sagemaker_model_data_url,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
    
        data_plane.raw_images_bucket.grant_read(batch_inference)
        batch_results_bucket.grant_read_write(batch_inference)

        results_processor = lambda_.Function(
            self,
            "BatchResultsProcessor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/batch_results_processor"),
            timeout=Duration.seconds(30),
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "DYNAMO_TABLE_NAME": data_plane.telemetry_table.table_name,
            },
        )

        batch_results_bucket.grant_read(results_processor)
        data_plane.telemetry_table.grant_read_write_data(results_processor)

        batch_results_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(results_processor),
        )

        batch_schedule = events.Rule(
            self,
            "BatchInferenceSchedule",
            schedule=events.Schedule.cron(minute="5", hour="*"),
            targets=[targets.LambdaFunction(batch_inference)],
            description="Run Lambda batch transform five minutes past every hour.",
        )

        return MlInferenceResources(
            batch_launcher_lambda=batch_inference,
            results_processor_lambda=results_processor,
            results_bucket=batch_results_bucket,
            model_artifact_bucket=model_bucket,
            batch_schedule=batch_schedule,
        )

