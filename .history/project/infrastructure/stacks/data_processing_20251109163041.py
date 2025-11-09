from dataclasses import dataclass

from aws_cdk import Duration, aws_lambda as lambda_, aws_lambda_event_sources as lambda_event_sources
from constructs import Construct

from infrastructure.config.app_context import AppContext
from infrastructure.stacks.data_plane import DataPlaneResources
from infrastructure.stacks.notifications import NotificationResources


@dataclass
class DataProcessingResources:
    stream_processor: lambda_.Function


class DataProcessingConstruct(Construct):
    """Lambda stream processor that aggregates telemetry into DynamoDB."""

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
    ) -> DataProcessingResources:
        processor_fn = lambda_.Function(
            self,
            "StreamProcessorFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_src/stream_processor"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "DYNAMO_TABLE_NAME": data_plane.telemetry_table.table_name,
                "ALERT_THRESHOLD": str(app_context.config.alert_threshold),
                "SNS_TOPIC_ARN": notifications.alert_topic.topic_arn,
            },
        )

        data_plane.telemetry_table.grant_write_data(processor_fn)
        data_plane.telemetry_stream.grant_read(processor_fn)
        notifications.alert_topic.grant_publish(processor_fn)

        processor_fn.add_event_source(
            lambda_event_sources.KinesisEventSource(
                data_plane.telemetry_stream,
                batch_size=100,
                starting_position=lambda_.StartingPosition.LATEST,
                bisect_batch_on_error=True,
                retry_attempts=3,
            )
        )

        return DataProcessingResources(stream_processor=processor_fn)

