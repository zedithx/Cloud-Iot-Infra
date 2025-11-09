from dataclasses import dataclass

from aws_cdk import Duration, aws_iam as iam, aws_iot as iot, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources


@dataclass
class IotIngestResources:
    presign_lambda: lambda_.Function
    device_policy: iot.CfnPolicy
    telemetry_topic_rule: iot.CfnTopicRule


class IotIngestConstruct(Construct):
    """Creates IoT Core scaffolding and Lambda to mint S3 presigned URLs for edge devices."""

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
    ) -> IotIngestResources:
        presign_function = self._create_presign_lambda(data_plane)

        account = app_context.env.account or "*"
        region = app_context.env.region or "*"

        policy_document = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    actions=["iot:Connect"],
                    resources=[
                        f"arn:aws:iot:{region}:{account}:client/${{iot:ClientId}}"
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "iot:Publish",
                        "iot:Receive",
                        "iot:Subscribe",
                    ],
                    resources=[
                        f"arn:aws:iot:{region}:{account}:topic/leaf/telemetry/*",
                        f"arn:aws:iot:{region}:{account}:topic/leaf/commands/*",
                        f"arn:aws:iot:{region}:{account}:topicfilter/leaf/telemetry/*",
                        f"arn:aws:iot:{region}:{account}:topicfilter/leaf/commands/*",
                    ],
                ),
            ]
        )

        device_policy = iot.CfnPolicy(
            self,
            "LeafDevicePolicy",
            policy_document=policy_document.to_json(),
            policy_name=f"{app_context.stage}-leaf-device",
        )

        topic_rule_role = iam.Role(
            self,
            "IotKinesisRole",
            assumed_by=iam.ServicePrincipal("iot.amazonaws.com"),
            inline_policies={
                "KinesisWrite": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["kinesis:PutRecord", "kinesis:PutRecords"],
                            resources=[data_plane.telemetry_stream.stream_arn],
                        )
                    ]
                )
            },
        )

        telemetry_topic_rule = iot.CfnTopicRule(
            self,
            "TelemetryRule",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                actions=[
                    iot.CfnTopicRule.ActionProperty(
                        kinesis=iot.CfnTopicRule.KinesisActionProperty(
                            role_arn=topic_rule_role.role_arn,
                            stream_name=data_plane.telemetry_stream.stream_name,
                            partition_key="${topic(2)}",
                        )
                    )
                ],
                sql="SELECT * FROM 'leaf/telemetry/+/data'",
                aws_iot_sql_version="2016-03-23",
                rule_disabled=False,
            ),
        )

        return IotIngestResources(
            presign_lambda=presign_function,
            device_policy=device_policy,
            telemetry_topic_rule=telemetry_topic_rule,
        )

    def _create_presign_lambda(self, data_plane: DataPlaneResources) -> lambda_.Function:
        function = lambda_.Function(
            self,
            "PresignUrlFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/presign_url"),
            timeout=Duration.seconds(10),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "RAW_BUCKET_NAME": data_plane.raw_images_bucket.bucket_name,
                "PRESIGN_TTL_SECONDS": "900",
            },
        )

        data_plane.raw_images_bucket.grant_put(function)
        data_plane.raw_images_bucket.grant_read(function)

        return function

