from dataclasses import dataclass

from aws_cdk import aws_sns as sns, aws_sns_subscriptions as subscriptions
from constructs import Construct

from infra.config.app_context import AppContext


@dataclass
class NotificationResources:
    alert_topic: sns.Topic


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

        alert_topic.add_subscription(
            subscriptions.EmailSubscription(app_context.config.alert_email)
        )

        return NotificationResources(alert_topic=alert_topic)

