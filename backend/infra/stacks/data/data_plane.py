from dataclasses import dataclass

from aws_cdk import RemovalPolicy, aws_dynamodb as dynamodb, aws_iam as iam, aws_kms as kms, aws_s3 as s3
from constructs import Construct

from infra.config.app_context import AppContext


@dataclass
class DataPlaneResources:
    raw_images_bucket: s3.Bucket
    processed_assets_bucket: s3.Bucket
    telemetry_table: dynamodb.Table
    shared_data_access_policy: iam.ManagedPolicy


class DataPlaneConstruct(Construct):
    """Provision shared data storage, streaming, and baseline IAM policies."""

    def __init__(self, scope: Construct, construct_id: str, *, app_context: AppContext) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_data_plane(app_context)

    def _create_data_plane(self, app_context: AppContext) -> DataPlaneResources:
        removal_policy = (
            RemovalPolicy.RETAIN if app_context.stage == "prod" else RemovalPolicy.DESTROY
        )

        encryption_key = kms.Key(
            self,
            "DataPlaneKey",
            enable_key_rotation=True,
            removal_policy=removal_policy,
        )

        raw_images_bucket = s3.Bucket(
            self,
            "RawLeafImagesBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=encryption_key,
            removal_policy=removal_policy,
            auto_delete_objects=app_context.stage != "prod",
        )

        processed_assets_bucket = s3.Bucket(
            self,
            "ProcessedAssetsBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=encryption_key,
            removal_policy=removal_policy,
            auto_delete_objects=app_context.stage != "prod",
        )

        telemetry_table = dynamodb.Table(
            self,
            "TelemetryTable",
            table_name=f"{app_context.stage}-telemetry",
            partition_key=dynamodb.Attribute(
                name="deviceId",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            removal_policy=removal_policy,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
        )

        shared_policy = iam.ManagedPolicy(
            self,
            "DataPlaneSharedPolicy",
            statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                    ],
                    resources=[
                        raw_images_bucket.arn_for_objects("*"),
                        processed_assets_bucket.arn_for_objects("*"),
                    ],
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket"],
                    resources=[
                        raw_images_bucket.bucket_arn,
                        processed_assets_bucket.bucket_arn,
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:DeleteItem",
                    ],
                    resources=[telemetry_table.table_arn],
                ),
                iam.PolicyStatement(
                    actions=[
                        "kms:Encrypt",
                        "kms:Decrypt",
                        "kms:GenerateDataKey*",
                    ],
                    resources=[encryption_key.key_arn],
                ),
            ],
        )

        return DataPlaneResources(
            raw_images_bucket=raw_images_bucket,
            processed_assets_bucket=processed_assets_bucket,
            telemetry_table=telemetry_table,
            shared_data_access_policy=shared_policy,
        )

