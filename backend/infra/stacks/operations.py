from dataclasses import dataclass

from aws_cdk import Duration, aws_cloudwatch as cloudwatch, aws_ecs as ecs, aws_secretsmanager as secretsmanager, aws_ssm as ssm
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.api.api_service import ApiServiceResources
from infra.stacks.data.data_processing import DataProcessingResources
from infra.stacks.ml.ml_inference import MlInferenceResources


@dataclass
class OperationsResources:
    alert_threshold_parameter: ssm.StringParameter
    fastapi_secret: secretsmanager.Secret
    alarms: list[cloudwatch.Alarm]


class OperationsConstruct(Construct):
    """Centralized operational assets such as parameters, secrets, and alarms."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        data_processing: DataProcessingResources,
        api_service: ApiServiceResources,
        ml_inference: MlInferenceResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            data_processing=data_processing,
            api_service=api_service,
            ml_inference=ml_inference,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        data_processing: DataProcessingResources,
        api_service: ApiServiceResources,
        ml_inference: MlInferenceResources,
    ) -> OperationsResources:
        threshold_parameter = ssm.StringParameter(
            self,
            "AlertThresholdParameter",
            parameter_name=f"/{app_context.stage}/alert-threshold",
            string_value=str(app_context.config.alert_threshold),
            description="Threshold for disease detection alerts.",
        )

        fastapi_secret = secretsmanager.Secret(
            self,
            "FastApiServiceSecret",
            secret_name=f"/{app_context.stage}/fastapi/api-key",
            description="API key used by FastAPI service for protected operations.",
        )

        if api_service.container:
            api_service.container.add_secret(
                "ApiKey",
                ecs.Secret.from_secrets_manager(fastapi_secret),
            )

        alarms: list[cloudwatch.Alarm] = []

        stream_error_alarm = cloudwatch.Alarm(
            self,
            "StreamProcessorErrors",
            metric=data_processing.stream_processor.metric_errors(
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            alarm_description="Alerts when the stream processor Lambda reports errors.",
        )
        alarms.append(stream_error_alarm)

        inference_alarm = cloudwatch.Alarm(
            self,
            "InferenceErrors",
            metric=ml_inference.inference_lambda.metric_errors(
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            alarm_description="Alerts when inference Lambda reports errors.",
        )
        alarms.append(inference_alarm)

        alb_unhealthy_alarm = cloudwatch.Alarm(
            self,
            "AlbUnhealthyHosts",
            metric=api_service.load_balancer.metric_unhealthy_host_count(
                period=Duration.minutes(5)
            ),
            threshold=1,
            evaluation_periods=1,
            datapoints_to_alarm=1,
            alarm_description="Alerts when the ALB target group reports unhealthy hosts.",
        )
        alarms.append(alb_unhealthy_alarm)

        return OperationsResources(
            alert_threshold_parameter=threshold_parameter,
            fastapi_secret=fastapi_secret,
            alarms=alarms,
        )

