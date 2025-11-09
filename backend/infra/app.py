#!/usr/bin/env python3
import aws_cdk as cdk

from infra.config.app_context import AppContext
from infra.infrastructure_stack import InfrastructureStack


app = cdk.App()
app_context = AppContext(app)

InfrastructureStack(
    app,
    f"{app_context.stage}-infrastructure",
    env=app_context.env,
    app_context=app_context,
)

app.synth()

