from dataclasses import dataclass

from aws_cdk import (
    Duration,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_sagemaker as sagemaker,
)
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources


@dataclass
class MlInferenceResources:
    batch_launcher_lambda: lambda_.Function
    results_processor_lambda: lambda_.Function
    model: sagemaker.CfnModel
    results_bucket: s3.Bucket
    model_artifact_bucket: s3.Bucket
    batch_schedule: events.Rule


class MlInferenceConstruct(Construct):
    """Sets up SageMaker batch transform infrastructure and schedules periodic jobs."""

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
                s3.RemovalPolicy.RETAIN if app_context.stage == "prod" else s3.RemovalPolicy.DESTROY
            ),
        )

        sagemaker_role = iam.Role(
            self,
            "BatchTransformRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
        )
        data_plane.raw_images_bucket.grant_read(sagemaker_role)
        batch_results_bucket.grant_read_write(sagemaker_role)

        model_bucket = s3.Bucket(
            self,
            "ModelArtifactBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            auto_delete_objects=app_context.stage != "prod",
            removal_policy=(
                s3.RemovalPolicy.RETAIN if app_context.stage == "prod" else s3.RemovalPolicy.DESTROY
            ),
        )
        model_bucket.grant_read(sagemaker_role)

        model = sagemaker.CfnModel(
            self,
            "BatchTransformModel",
            execution_role_arn=sagemaker_role.role_arn,
            primary_container=sagemaker.CfnModel.ContainerDefinitionProperty(
                image=app_context.sagemaker_image_uri,
                model_data_url=app_context.config.sagemaker_model_data_url,
            ),
            model_name=f"{app_context.stage}-leaf-disease-model",
        )

        batch_launcher = lambda_.Function(
            self,
            "BatchTransformLauncher",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/batch_launcher"),
            timeout=Duration.minutes(5),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "MODEL_NAME": model.model_name,
                "SAGEMAKER_ROLE_ARN": sagemaker_role.role_arn,
                "RAW_BUCKET": data_plane.raw_images_bucket.bucket_name,
                "BATCH_RESULTS_BUCKET": batch_results_bucket.bucket_name,
                "STAGE": app_context.stage,
            },
        )

        batch_launcher.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateTransformJob",
                    "sagemaker:DescribeTransformJob",
                    "sagemaker:StopTransformJob",
                ],
                resources=["*"],
            )
        )
        data_plane.raw_images_bucket.grant_read(batch_launcher)
        batch_results_bucket.grant_read_write(batch_launcher)

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
            "BatchTransformSchedule",
            schedule=events.Schedule.cron(minute="5", hour="*"),
            targets=[targets.LambdaFunction(batch_launcher)],
            description="Run SageMaker batch transform five minutes past every hour.",
        )

        return MlInferenceResources(
            batch_launcher_lambda=batch_launcher,
            results_processor_lambda=results_processor,
            model=model,
            results_bucket=batch_results_bucket,
            model_artifact_bucket=model_bucket,
            batch_schedule=batch_schedule,
        )

