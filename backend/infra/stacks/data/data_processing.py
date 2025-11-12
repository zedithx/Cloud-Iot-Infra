from dataclasses import dataclass

from aws_cdk import Duration, aws_lambda as lambda_, aws_logs as logs
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources


@dataclass
class DataProcessingResources:
    ingestion_lambda: lambda_.Function


class DataProcessingConstruct(Construct):
    """Lambda handler invoked by IoT Core to persist telemetry readings."""

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
    ) -> DataProcessingResources:
        ingestion_fn = lambda_.Function(
            self,
            "TelemetryIngestionFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/stream_processor"),
            timeout=Duration.seconds(30),
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "DYNAMO_TABLE_NAME": data_plane.telemetry_table.table_name,
            },
        )

        data_plane.telemetry_table.grant_read_write_data(ingestion_fn)

        return DataProcessingResources(ingestion_lambda=ingestion_fn)

