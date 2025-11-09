from dataclasses import dataclass

from aws_cdk import (
    Duration,
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
from infra.stacks.networking.networking import NetworkingResources


@dataclass
class MlInferenceResources:
    inference_lambda: lambda_.Function
    sagemaker_endpoint: sagemaker.CfnEndpoint


class MlInferenceConstruct(Construct):
    """Sets up SageMaker model hosting and the Lambda invoker wired to S3 events."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        networking: NetworkingResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            data_plane=data_plane,
            networking=networking,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        networking: NetworkingResources,
    ) -> MlInferenceResources:
        sagemaker_role = iam.Role(
            self,
            "SageMakerExecutionRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            inline_policies={
                "ModelArtifactAccess": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["s3:GetObject"],
                            resources=[
                                data_plane.processed_assets_bucket.arn_for_objects("*"),
                                data_plane.raw_images_bucket.arn_for_objects("*"),
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["s3:ListBucket"],
                            resources=[
                                data_plane.raw_images_bucket.bucket_arn,
                                data_plane.processed_assets_bucket.bucket_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*"],
                            resources=["*"],
                        ),
                    ]
                )
            },
        )

        model_name = f"{app_context.stage}-leaf-disease-model"

        model = sagemaker.CfnModel(
            self,
            "DiseaseDetectionModel",
            execution_role_arn=sagemaker_role.role_arn,
            primary_container=sagemaker.CfnModel.ContainerDefinitionProperty(
                image=app_context.sagemaker_image_uri,
                model_data_url=app_context.config.sagemaker_model_data_url,
                environment={
                    "SAGEMAKER_CONTAINER_LOG_LEVEL": "20",
                    "SAGEMAKER_REGION": app_context.env.region or "us-east-1",
                },
            ),
            vpc_config=sagemaker.CfnModel.VpcConfigProperty(
                security_group_ids=[networking.sagemaker_security_group.security_group_id],
                subnets=[subnet.subnet_id for subnet in networking.vpc.public_subnets],
            ),
            model_name=model_name,
        )

        endpoint_config = sagemaker.CfnEndpointConfig(
            self,
            "DiseaseDetectionEndpointConfig",
            production_variants=[
                sagemaker.CfnEndpointConfig.ProductionVariantProperty(
                    model_name=model.model_name,
                    variant_name="AllTraffic",
                    initial_instance_count=1,
                    instance_type="ml.m5.large",
                )
            ],
            endpoint_config_name=f"{app_context.stage}-leaf-disease-config",
        )
        endpoint_config.add_dependency(model)

        endpoint = sagemaker.CfnEndpoint(
            self,
            "DiseaseDetectionEndpoint",
            endpoint_name=f"{app_context.stage}-leaf-disease-endpoint",
            endpoint_config_name=endpoint_config.endpoint_config_name,
        )

        inference_lambda = lambda_.Function(
            self,
            "InferenceFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/inference"),
            timeout=Duration.seconds(30),
            memory_size=512,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "SAGEMAKER_ENDPOINT_NAME": endpoint.endpoint_name,
                "PROCESSED_BUCKET": data_plane.processed_assets_bucket.bucket_name,
            },
        )

        data_plane.raw_images_bucket.grant_read(inference_lambda)
        data_plane.processed_assets_bucket.grant_write(inference_lambda)

        inference_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=[endpoint.attr_endpoint_arn],
            )
        )

        data_plane.raw_images_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(inference_lambda),
            s3.NotificationKeyFilter(prefix=f"{app_context.stage}/"),
        )

        return MlInferenceResources(
            inference_lambda=inference_lambda,
            sagemaker_endpoint=endpoint,
        )

