from django.test import TestCase
from apps.agents.models import Agent, AgentNotification


class AgentNotificationSchemaRegressionTest(TestCase):
    """
    White-Box Regression Test for AgentNotification schema integrity.
    Verifies that AgentNotification can be filtered and created with its foreign key `agent`.
    """

    def setUp(self):
        self.agent = Agent.objects.create(
            fullname="Notification Test Agent",
            email="notif_test@padosiagent.test",
            mobile="9898989898",
            agent_pincode="380001",
            status="active",
        )

    def test_filter_agent_notifications_by_agent(self):
        """
        Verify that AgentNotification can be queried by `agent`.
        Without migration 0041, the test database lacks `agent_id` column on `agent_notifications`.
        """
        # Should execute without `OperationalError: no such column: agent_notifications.agent_id`
        notifications = list(AgentNotification.objects.filter(agent=self.agent, is_read=False))
        self.assertEqual(notifications, [])

