from dataclasses import dataclass

from aws_cdk import aws_iam as iam, aws_iot as iot, aws_lambda as lambda_
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources
from infra.stacks.data.data_processing import DataProcessingResources


@dataclass
class IotIngestResources:
    device_policy: iot.CfnPolicy
    telemetry_topic_rule: iot.CfnTopicRule


class IotIngestConstruct(Construct):
    """Creates IoT Core scaffolding for device connectivity and telemetry ingestion."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        data_processing: DataProcessingResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            data_plane=data_plane,
            data_processing=data_processing,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        data_plane: DataPlaneResources,
        data_processing: DataProcessingResources,
    ) -> IotIngestResources:
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

        telemetry_topic_rule = iot.CfnTopicRule(
            self,
            "TelemetryRule",
            topic_rule_payload=iot.CfnTopicRule.TopicRulePayloadProperty(
                actions=[
                    iot.CfnTopicRule.ActionProperty(
                        lambda_=iot.CfnTopicRule.LambdaActionProperty(
                            function_arn=data_processing.ingestion_lambda.function_arn
                        )
                    )
                ],
                sql="SELECT * FROM 'leaf/telemetry/+/data'",
                aws_iot_sql_version="2016-03-23",
                rule_disabled=False,
            ),
        )

        lambda_.CfnPermission(
            self,
            "AllowIotInvokeTelemetryLambda",
            action="lambda:InvokeFunction",
            function_name=data_processing.ingestion_lambda.function_name,
            principal="iot.amazonaws.com",
            source_arn=telemetry_topic_rule.attr_arn,
        )

        # Photo uploads are now handled via presigned URLs sent in capture commands
        # Devices upload directly to S3, so no IoT rule needed

        return IotIngestResources(
            device_policy=device_policy,
            telemetry_topic_rule=telemetry_topic_rule,
        )

