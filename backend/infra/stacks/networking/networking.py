from dataclasses import dataclass

from aws_cdk import aws_ec2 as ec2
from constructs import Construct

from infra.config.app_context import AppContext


@dataclass
class NetworkingResources:
    """Returned networking artifacts for the broader infrastructure stack."""

    vpc: ec2.Vpc
    alb_security_group: ec2.SecurityGroup
    ecs_security_group: ec2.SecurityGroup
    lambda_security_group: ec2.SecurityGroup
    sagemaker_security_group: ec2.SecurityGroup


class NetworkingConstruct(Construct):
    """Defines the shared VPC, public subnets, and foundational security groups."""

    def __init__(self, scope: Construct, construct_id: str, *, app_context: AppContext) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_networking(app_context)

    def _create_networking(self, app_context: AppContext) -> NetworkingResources:
        vpc = ec2.Vpc(
            self,
            "ApplicationVpc",
            ip_addresses=ec2.IpAddresses.cidr(app_context.config.vpc_cidr),
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
            nat_gateways=0,
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # Gateway endpoints provide private connectivity to core AWS services.
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)],
        )

        vpc.add_gateway_endpoint(
            "DynamoEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)],
        )

        alb_sg = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=vpc,
            description="Allows inbound HTTP(S) traffic to the public load balancer.",
            allow_all_outbound=True,
        )
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP inbound",
        )
        alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv6(),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP inbound (IPv6)",
        )

        ecs_sg = ec2.SecurityGroup(
            self,
            "EcsServiceSecurityGroup",
            vpc=vpc,
            description="Controls traffic to FastAPI ECS tasks.",
            allow_all_outbound=True,
        )
        ecs_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(8000),
            description="Allow traffic from ALB to FastAPI container",
        )

        lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSecurityGroup",
            vpc=vpc,
            description="Allows Lambda functions to communicate with VPC resources.",
            allow_all_outbound=True,
        )

        sagemaker_sg = ec2.SecurityGroup(
            self,
            "SageMakerSecurityGroup",
            vpc=vpc,
            description="Access control for SageMaker endpoints within the VPC.",
            allow_all_outbound=True,
        )

        return NetworkingResources(
            vpc=vpc,
            alb_security_group=alb_sg,
            ecs_security_group=ecs_sg,
            lambda_security_group=lambda_sg,
            sagemaker_security_group=sagemaker_sg,
        )

