"""Rendered-HTML checks for payment_callback and simulator_page (audit WA-S template move)."""

import datetime
import unittest
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.wa_agent_bot import views

ACTIVATE = "apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment"


class PaymentCallbackHtmlTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self):
        request = self.factory.get(
            "/wa-bot/payment-callback/?razorpay_payment_id=pay_1&razorpay_payment_link_id=plink_1"
        )
        return views.payment_callback(request)

    def _assert_common(self, content):
        for fragment in (
            "<title>Payment Received — PadosiAgent</title>",
            "Payment Received!",
            "Credentials Sent to WhatsApp & Email",
            "Admin Approval",
            'href="/wa-bot/simulator/" class="btn-whatsapp"',
            '/agent-login/" class="btn-primary"',
            "Proceed to Agent Login",
            "function copyText(txt, btn) {",
            "setTimeout(function() {",
            "@keyframes popIn {",
            "0% { transform: scale(0.6); opacity: 0; }",
            "PadosiAgent &bull; India's #1 Insurance Agent Network",
            "Default password is your 10-digit registered mobile number",
        ):
            self.assertIn(fragment, content)
        self.assertNotIn("{{", content)
        self.assertNotIn("{%", content)

    @patch("apps.agents.models.AgentSubscription.objects")
    def test_no_subscription(self, mock_objs):
        mock_objs.filter.return_value.first.return_value = None
        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")
        content = response.content.decode()
        self._assert_common(content)
        self.assertIn("Thank you, <strong>Agent</strong>!", content)
        self.assertIn("Sent to Registered Number", content)
        self.assertIn("Sent to registered email", content)
        self.assertIn("<span>Your registered email</span>", content)
        self.assertIn("<span>Membership Plan</span>", content)
        self.assertNotIn('class="copy-btn" onclick', content)

    @patch("apps.agents.services.razorpay_checkout.razorpay_client", return_value=None)
    @patch("apps.agents.models.AgentSubscription.objects")
    @patch(ACTIVATE)
    def test_unverified_hides_account(self, mock_activate, mock_objs, _client):
        sub = MagicMock(
            payment_status="pending",
            razorpay_order_id="plink_1",
            selected_plan="starter",
        )
        sub.agent.email = "victim@example.com"
        sub.agent.fullname = "Victim"
        mock_objs.filter.return_value.first.return_value = sub
        content = self._get().content.decode()
        mock_activate.assert_not_called()
        self._assert_common(content)
        self.assertNotIn("victim@example.com", content)
        self.assertNotIn("Victim", content)
        self.assertIn("Thank you, <strong>Agent</strong>!", content)
        self.assertIn("<span>starter</span>", content)

    @patch("apps.agents.models.AgentSubscription.objects")
    @patch(ACTIVATE)
    def test_completed_shows_agent(self, mock_activate, mock_objs):
        sub = MagicMock(
            payment_status="completed",
            razorpay_order_id="plink_1",
            selected_plan="<i>pro</i>",
        )
        sub.agent.email = "ravi@example.com"
        sub.agent.fullname = "<b>Ravi</b>"
        sub.agent.mobile = "98765 43210"
        mock_objs.filter.return_value.first.return_value = sub
        content = self._get().content.decode()
        mock_activate.assert_called_once()
        self._assert_common(content)
        self.assertIn("Thank you, <strong>&lt;b&gt;Ravi&lt;/b&gt;</strong>!", content)
        self.assertNotIn("<b>Ravi</b>", content)
        self.assertIn("Sent to +91 98•••••210", content)
        self.assertIn("Sent to ravi@example.com", content)
        self.assertIn("<span>ravi@example.com</span>", content)
        self.assertIn(
            '<button type="button" class="copy-btn" onclick="copyText(&quot;ravi@example.com&quot;, this)">Copy</button>',
            content,
        )
        self.assertIn("<span>&lt;i&gt;pro&lt;/i&gt;</span>", content)


@override_settings(DEBUG=True)
@patch("apps.admin_panel.auth._get_admin_from_session", return_value={"id": 1})
class SimulatorPageHtmlTests(SimpleTestCase):
    def _render(self, enabled, session):
        from apps.wa_agent_bot import simulator_views

        request = RequestFactory().get("/wa-bot/simulator/")
        with (
            patch.object(simulator_views, "is_wa_bot_enabled", return_value=enabled),
            patch.object(simulator_views.WaBotSession, "objects") as objs,
        ):
            objs.filter.return_value.first.return_value = session
            response = simulator_views.simulator_page(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].split(";")[0], "text/html")
        return response.content.decode()

    def _assert_common(self, content):
        for fragment in (
            "<title>WhatsApp Bot Live Simulator — PadosiAgent</title>",
            'Test Phone: <strong style="color: #25D366;">+919876543210</strong>',
            'href="/admin/settings/general/"',
            'href="/admin/wa_agent_bot/wabotsession/"',
            'href="/admin/wa_agent_bot/wabotmessagelog/"',
            'href="/wa-bot/health/"',
            "fetch('/wa-bot/simulator/poll/?phone=' + encodeURIComponent('919876543210')",
            "body: JSON.stringify({ message: text, phone: '919876543210' })",
            "body: JSON.stringify({ phone: '919876543210' })",
            "fetch('/wa-bot/simulator/send/', {",
            "fetch('/wa-bot/simulator/reset/', {",
            "fetch('/wa-bot/simulator/simulate-payment/', {",
            "fetch('/wa-bot/simulator/toggle/', {",
            "s = s.replace(/\\*([^\\*]+)\\*/g, '<strong>$1</strong>');",
            's = s.replace(/(https?:\\/\\/[^\\s<]+)/g, \'<a href="$1" target="_blank">$1</a>\');',
            's += `<a href="${rzpMatch[1]}" target="_blank" class="pay-btn">',
            "row.className = `msg-row ${direction === 'out' ? 'out' : 'in'}`;",
            "{hour: '2-digit', minute:'2-digit'}",
            "Live Simulator!\\n\\nType *Hi* below",
            "PadosiAgent Official Bot",
            "Simulate Payment Success",
            ".bubble.out {",
        ):
            self.assertIn(fragment, content)
        self.assertRegex(content, r"'X-CSRFToken': '[A-Za-z0-9]{32,}'")
        self.assertNotIn("{{", content)
        self.assertNotIn("{%", content)

    def test_enabled_no_session(self, _admin):
        content = self._render(True, None)
        self._assert_common(content)
        self.assertIn('class="status-pill status-active"', content)
        self.assertIn("Master Switch: ON</span>", content)
        self.assertIn('class="disabled-notice" style="display: none;"', content)
        self.assertIn("const initialLogs = [];", content)
        self.assertIn("let lastMessageId = 0;", content)

    def test_disabled_with_logs(self, _admin):
        log = MagicMock(
            id=42,
            direction="out",
            content="hello *there*",
            created_at=datetime.datetime(2026, 1, 1, 9, 5),
        )
        session = MagicMock()
        session.message_logs.order_by.return_value = [log]
        content = self._render(False, session)
        self._assert_common(content)
        self.assertIn('class="status-pill status-disabled"', content)
        self.assertIn("Master Switch: OFF</span>", content)
        self.assertIn('class="disabled-notice" style="display: block;"', content)
        self.assertIn('"content": "hello *there*"', content)
        self.assertIn('"time": "09:05 AM"', content)
        self.assertIn("let lastMessageId = 42;", content)

    def test_log_content_cannot_close_script(self, _admin):
        log = MagicMock(id=7, direction="in", content="</script><img src=x onerror=alert(1)>",
                        created_at=datetime.datetime(2026, 1, 1, 9, 5))
        session = MagicMock()
        session.message_logs.order_by.return_value = [log]
        content = self._render(True, session)
        self.assertNotIn("</script><img", content)
        self.assertIn(r"\u003C/script\u003E\u003Cimg", content)
