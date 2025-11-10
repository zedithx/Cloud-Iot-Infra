from dataclasses import dataclass
from pathlib import Path

from aws_cdk import (
    Duration,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_ecr_assets as ecr_assets,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_logs as logs,
)
from constructs import Construct

from infra.config.app_context import AppContext
from infra.stacks.data.data_plane import DataPlaneResources
from infra.stacks.networking.networking import NetworkingResources


@dataclass
class ApiServiceResources:
    cluster: ecs.Cluster
    service: ecs.FargateService
    load_balancer: elbv2.ApplicationLoadBalancer
    http_api: apigwv2.HttpApi
    task_definition: ecs.FargateTaskDefinition
    container: ecs.ContainerDefinition
    target_group: elbv2.ApplicationTargetGroup


class ApiServiceConstruct(Construct):
    """ECS Fargate FastAPI service exposed via ALB and API Gateway HTTP API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        app_context: AppContext,
        networking: NetworkingResources,
        data_plane: DataPlaneResources,
    ) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(
            app_context=app_context,
            networking=networking,
            data_plane=data_plane,
        )

    def _create_resources(
        self,
        *,
        app_context: AppContext,
        networking: NetworkingResources,
        data_plane: DataPlaneResources,
    ) -> ApiServiceResources:
        cluster = ecs.Cluster(
            self,
            "ApiCluster",
            vpc=networking.vpc,
            container_insights=True,
        )

        task_definition = ecs.FargateTaskDefinition(
            self,
            "FastApiTaskDef",
            cpu=512,
            memory_limit_mib=1024,
        )

        if app_context.config.fastapi_image_uri:
            container_image = ecs.ContainerImage.from_registry(
                app_context.config.fastapi_image_uri
            )
        else:
            container_image = ecs.ContainerImage.from_asset(
                str(
                    Path(__file__).resolve().parents[3]
                    / "runtime"
                    / "ecs"
                    / "fastapi"
                ),
                platform=ecr_assets.Platform.LINUX_AMD64,
            )

        container = task_definition.add_container(
            "FastApiContainer",
            image=container_image,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="fastapi",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            environment={
                "APP_STAGE": app_context.stage,
                "TELEMETRY_TABLE": data_plane.telemetry_table.table_name,
                "ALLOWED_ORIGINS": app_context.config.allowed_origins,
            },
        )
        container.add_port_mappings(
            ecs.PortMapping(container_port=8000, protocol=ecs.Protocol.TCP)
        )

        service = ecs.FargateService(
            self,
            "FastApiService",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=1,
            assign_public_ip=True,
            security_groups=[networking.ecs_security_group],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        data_plane.telemetry_table.grant_read_write_data(service.task_definition.task_role)

        load_balancer = elbv2.ApplicationLoadBalancer(
            self,
            "ApiLoadBalancer",
            vpc=networking.vpc,
            internet_facing=True,
            security_group=networking.alb_security_group,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )
        listener = load_balancer.add_listener(
            "HttpListener",
            port=80,
            open=True,
        )
        target_group = listener.add_targets(
            "FargateTarget",
            port=8000,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
            ),
        )

        http_api = apigwv2.HttpApi(
            self,
            "CommandHttpApi",
            api_name=f"{app_context.stage}-command-api",
            create_default_stage=True,
        )

        vpc_link = apigwv2.VpcLink(
            self,
            "AlbVpcLink",
            vpc=networking.vpc,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
        )

        alb_integration = apigw_integrations.HttpAlbIntegration(
            "AlbIntegration",
            listener=listener,
            vpc_link=vpc_link,
        )

        http_api.add_routes(
            path="/{proxy+}",
            methods=[
                apigwv2.HttpMethod.GET,
                apigwv2.HttpMethod.POST,
                apigwv2.HttpMethod.PUT,
                apigwv2.HttpMethod.DELETE,
                apigwv2.HttpMethod.PATCH,
            ],
            integration=alb_integration,
        )

        return ApiServiceResources(
            cluster=cluster,
            service=service,
            load_balancer=load_balancer,
            http_api=http_api,
            task_definition=task_definition,
            container=container,
            target_group=target_group,
        )

