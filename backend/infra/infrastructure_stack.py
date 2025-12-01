from typing import Optional

from aws_cdk import Stack
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.api.api_service import ApiServiceConstruct, ApiServiceResources
from infra.stacks.data.data_plane import DataPlaneConstruct, DataPlaneResources
from infra.stacks.data.data_processing import DataProcessingConstruct, DataProcessingResources
from infra.stacks.iot.iot_ingest import IotIngestConstruct, IotIngestResources
from infra.stacks.ml.ml_inference import MlInferenceConstruct, MlInferenceResources
from infra.stacks.networking.networking import NetworkingConstruct, NetworkingResources
from infra.stacks.notifications import NotificationResources, NotificationsConstruct
from infra.stacks.operations import OperationsConstruct, OperationsResources
from infra.stacks.scheduling.scheduling import SchedulingConstruct, SchedulingResources


class InfrastructureStack(Stack):
    """Top-level stack wiring together all infrastructure constructs."""

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
        self.notifications: NotificationResources = NotificationsConstruct(
            self,
            "Notifications",
            app_context=app_context,
        ).resources
        self.data_processing: DataProcessingResources = DataProcessingConstruct(
            self,
            "DataProcessing",
            app_context=app_context,
            data_plane=self.data_plane,
        ).resources
        self.iot_ingest: IotIngestResources = IotIngestConstruct(
            self,
            "IotIngest",
            app_context=app_context,
            data_plane=self.data_plane,
            data_processing=self.data_processing,
        ).resources
        self.scheduling: SchedulingResources = SchedulingConstruct(
            self,
            "Scheduling",
            app_context=app_context,
            data_plane=self.data_plane,
            notifications=self.notifications,
        ).resources
        self.ml_inference: Optional[MlInferenceResources] = None
        if app_context.config.enable_ml_inference:
            self.ml_inference = MlInferenceConstruct(
                self,
                "MlInference",
                app_context=app_context,
                data_plane=self.data_plane,
            ).resources
        self.api_service: ApiServiceResources = ApiServiceConstruct(
            self,
            "ApiService",
            app_context=app_context,
            networking=self.networking,
            data_plane=self.data_plane,
        ).resources
        self.operations: OperationsResources = OperationsConstruct(
            self,
            "Operations",
            app_context=app_context,
            data_processing=self.data_processing,
            api_service=self.api_service,
            ml_inference=self.ml_inference,
        ).resources

