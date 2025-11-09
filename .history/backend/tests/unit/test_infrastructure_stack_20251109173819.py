import aws_cdk as core
import aws_cdk.assertions as assertions

from infra.config.app_context import AppContext
from infra.infrastructure_stack import InfrastructureStack


# example tests. To run these tests, uncomment this file along with the example
# resource in infra/infrastructure_stack.py
def test_sqs_queue_created():
    app = core.App(context={"stage": "test"})
    app_context = AppContext(app)
    stack = InfrastructureStack(app, "infrastructure", app_context=app_context)
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
