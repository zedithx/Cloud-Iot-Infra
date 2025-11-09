from aws_cdk import Stack
from constructs import Construct

from infrastructure.config.app_context import AppContext
from infrastructure.stacks.data_plane import DataPlaneConstruct, DataPlaneResources
from infrastructure.stacks.iot_ingest import IotIngestConstruct, IotIngestResources
from infrastructure.stacks.networking import NetworkingConstruct, NetworkingResources


class InfrastructureStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.app_context = app_context
        self.networking: NetworkingResources = NetworkingConstruct(
            self,
            "Networking",
            app_context=app_context,
        ).resources
        self.data_plane: DataPlaneResources = DataPlaneConstruct(
            self,
            "DataPlane",
            app_context=app_context,
        ).resources
        self.iot_ingest: IotIngestResources = IotIngestConstruct(
            self,
            "IotIngest",
            app_context=app_context,
            data_plane=self.data_plane,
        ).resources

        # The code that defines your stack goes here

        # example resource
        # queue = sqs.Queue(
        #     self, "InfrastructureQueue",
        #     visibility_timeout=Duration.seconds(300),
        # )
