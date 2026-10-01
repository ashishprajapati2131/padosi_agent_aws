"""Audit 2026-10-01 F-13: the reconcile page put agent / Razorpay values into
innerHTML and inline onclick strings unescaped (admin-side XSS)."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, AgentSubscription


class ReconcilePageEscapingTests(TestCase):
    def test_agent_email_is_not_placed_inside_an_inline_handler(self):
        from apps.admin_panel.views.payment_reconcile import payment_reconcile_dashboard
        agent = Agent.objects.create(fullname='Quote', email="a'+alert(1)+'@example.com", mobile='9000000093')
        AgentSubscription.objects.create(agent=agent, selected_plan="Starter's Plan",
                                         registration_amount='2359.00', payment_status='pending')
        request = RequestFactory().get('/admin/payments/reconcile/')
        request.session = {}
        with patch('apps.admin_panel.views.payment_reconcile._is_admin_authenticated', return_value=1):
            html = payment_reconcile_dashboard(request).content.decode()
        self.assertNotIn("loadAndInspect('", html)
        self.assertIn('onclick="loadAndInspect(this.dataset.email)"', html)
        self.assertIn('function esc(value)', html)
