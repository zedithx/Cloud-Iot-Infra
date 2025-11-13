from dataclasses import dataclass

from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

from infra.config.app_context import AppContext


@dataclass
class NotificationResources:
    alert_topic: sns.Topic
    email_lambda: lambda_.Function


class NotificationsConstruct(Construct):
    """SNS topics and subscriptions for alerting."""

    def __init__(self, scope: Construct, construct_id: str, *, app_context: AppContext) -> None:
        super().__init__(scope, construct_id)

        self.resources = self._create_resources(app_context)

    def _create_resources(self, app_context: AppContext) -> NotificationResources:
        alert_topic = sns.Topic(
            self,
            "AlertTopic",
            display_name=f"{app_context.stage.capitalize()} Leaf Disease Alerts",
            topic_name=f"{app_context.stage}-leaf-alerts",
        )

        from_email = app_context.config.ses_from_email or app_context.config.alert_email
        to_emails = app_context.config.ses_to_email or app_context.config.alert_email

        email_lambda = lambda_.Function(
            self,
            "AlertEmailRelay",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("runtime/lambdas/email_notifier"),
            timeout=Duration.seconds(30),
            memory_size=256,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "FROM_EMAIL": from_email,
                "TO_EMAILS": to_emails,
            },
        )

        email_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )

        alert_topic.add_subscription(subscriptions.LambdaSubscription(email_lambda))

        return NotificationResources(alert_topic=alert_topic, email_lambda=email_lambda)

