from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Optional

import aws_cdk as cdk


@dataclass(frozen=True)
class ApplicationEnvironmentConfig:
    """Holds environment-specific defaults for the application."""

    stage: str
    vpc_cidr: str
    alert_email: str
    sagemaker_model_data_url: str
    sagemaker_model_image_uri: str
    alert_threshold: float
    allowed_origins: str = "*"
    enable_ml_inference: bool = False
    ses_from_email: Optional[str] = None
    ses_to_email: Optional[str] = None
    account: Optional[str] = None
    region: Optional[str] = None
    fastapi_image_uri: Optional[str] = None


DEFAULT_ENV = ApplicationEnvironmentConfig(
    stage="dev",
    vpc_cidr="10.20.0.0/16",
    fastapi_image_uri=None,
    alert_email="aersijun@gmail.com",
    sagemaker_model_data_url="s3://placeholder-model-artifacts/model.tar.gz",
    sagemaker_model_image_uri="683313688378.dkr.ecr.{region}.amazonaws.com/kmeans:1",
    alert_threshold=0.8,
    allowed_origins="http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001,https://cloud-iot-infra.vercel.app",
    enable_ml_inference=False,
    ses_from_email="tangledsocialapp@gmail.com",
    region="ap-southeast-1",
    ses_to_email="aersijun@gmail.com",
)


class AppContext:
    """Encapsulates CDK app configuration, stage, and AWS environment resolution."""

    def __init__(self, app: cdk.App) -> None:
        self._stage = (
            app.node.try_get_context("stage")
            or os.getenv("CDK_STAGE")
            or "dev"
        )

        # Optional overrides can be provided via CDK context under the key "config".
        overrides = app.node.try_get_context("config") or {}
        config = DEFAULT_ENV
        if overrides:
            # Filter out any keys that are not defined on the dataclass
            valid_overrides = {
                key: value for key, value in overrides.items() if hasattr(config, key)
            }
            if valid_overrides:
                config = replace(config, **valid_overrides)

        # Ensure the stage attribute always reflects the context value we resolved.
        config = replace(config, stage=self._stage)

        account = config.account or os.getenv("CDK_DEFAULT_ACCOUNT")
        region = config.region or os.getenv("CDK_DEFAULT_REGION") or "us-east-1"

        self._config = config
        self._env = cdk.Environment(account=account, region=region)

    @property
    def sagemaker_image_uri(self) -> str:
        region = self.env.region or "us-east-1"
        return self.config.sagemaker_model_image_uri.format(region=region)

    @property
    def stage(self) -> str:
        return self._stage

    @property
    def env(self) -> cdk.Environment:
        return self._env

    @property
    def config(self) -> ApplicationEnvironmentConfig:
        return self._config

