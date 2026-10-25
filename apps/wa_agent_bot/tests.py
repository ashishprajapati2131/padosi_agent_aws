"""
Unit Tests for WhatsApp Agent Bot (wa_agent_bot)

Tests cover:
1. Input validators (name, email, mobile, state, pincode, experience, segments)
2. State machine transitions (welcome -> ask_fullname -> ask_email -> ... -> confirm)
3. Plan selection (Starter, Professional, Trial) and automated payment link delivery
4. Back navigation, cancel, and switching plans
5. Post-login bounded commands & polite out-of-scope rejection
6. Webhook request handling (OpenWA & Razorpay) and payment callbacks
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from django.test import RequestFactory

from apps.wa_agent_bot.models import WaBotSession
from apps.wa_agent_bot.services import validators
from apps.wa_agent_bot.services.state_machine import process_message
from apps.wa_agent_bot.services.post_login_handler import process_post_login_message
from apps.wa_agent_bot.services.payment_service import get_available_plans
from apps.wa_agent_bot import views


class ValidatorTests(unittest.TestCase):
    """Test individual field validation logic."""

    def test_validate_fullname(self):
        valid, val = validators.validate_fullname("Rajesh Sharma")
        self.assertTrue(valid)
        self.assertEqual(val, "Rajesh Sharma")

        valid, err = validators.validate_fullname("R")
        self.assertFalse(valid)

        valid, err = validators.validate_fullname("12345 67890")
        self.assertFalse(valid)

    def test_validate_email(self):
        valid, val = validators.validate_email("test@example.com")
        self.assertTrue(valid)
        self.assertEqual(val, "test@example.com")

        valid, err = validators.validate_email("invalid-email")
        self.assertFalse(valid)

    def test_validate_mobile(self):
        valid, val = validators.validate_mobile("9876543210")
        self.assertTrue(valid)
        self.assertEqual(val, "9876543210")

        valid, val = validators.validate_mobile("+91 98765-43210")
        self.assertTrue(valid)
        self.assertEqual(val, "9876543210")

        valid, err = validators.validate_mobile("12345")
        self.assertFalse(valid)

    def test_validate_state(self):
        valid, val = validators.validate_state_selection("1")
        self.assertTrue(valid)
        self.assertEqual(val, "Andhra Pradesh")

        valid, val = validators.validate_state_selection("Maharashtra")
        self.assertTrue(valid)
        self.assertEqual(val, "Maharashtra")

        valid, err = validators.validate_state_selection("InvalidState123")
        self.assertFalse(valid)

    def test_validate_pincode(self):
        valid, val = validators.validate_pincode("380001")
        self.assertTrue(valid)
        self.assertEqual(val, "380001")

        valid, err = validators.validate_pincode("1234")
        self.assertFalse(valid)

    def test_validate_experience(self):
        valid, val = validators.validate_experience_selection("2")
        self.assertTrue(valid)
        self.assertEqual(val, "2-5 years")

        valid, err = validators.validate_experience_selection("99")
        self.assertFalse(valid)

    def test_validate_segments(self):
        valid, val = validators.validate_segments_selection("1, 3")
        self.assertTrue(valid)
        self.assertIn("health", val)
        self.assertIn("motor", val)


class StateMachineFlowTests(unittest.TestCase):
    """Test state machine transitions through registration, plan selection & payment."""

    def setUp(self):
        self.session = MagicMock()
        self.session.phone_number = "919876543210"
        self.session.state = WaBotSession.STATE_WELCOME
        self.session.registration_data = {}
        self.session.is_registered = False
        self.session.is_logged_in = False
        self.session.agent = None
        self.session.save = MagicMock()

    @patch('apps.agents.models.Agent.objects')
    def test_full_registration_and_plan_flow(self, mock_agent_objects):
        mock_agent_objects.filter.return_value.exists.return_value = False

        # 1. Start / Hi
        reply = process_message(self.session, "hi")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_FULLNAME)
        self.assertIn("Step 1 of 7", reply)

        # 2. Enter full name
        reply = process_message(self.session, "Amit Kumar")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_EMAIL)
        self.assertEqual(self.session.registration_data.get('fullname'), "Amit Kumar")

        # 3. Enter email
        reply = process_message(self.session, "amit@example.com")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_MOBILE)
        self.assertEqual(self.session.registration_data.get('email'), "amit@example.com")

        # 4. Enter mobile
        reply = process_message(self.session, "9876543210")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_STATE)
        self.assertEqual(self.session.registration_data.get('mobile'), "9876543210")

        # 5. Enter state
        reply = process_message(self.session, "Gujarat")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_PINCODE)
        self.assertEqual(self.session.registration_data.get('state'), "Gujarat")

        # 6. Enter pincode
        reply = process_message(self.session, "380001")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_EXPERIENCE)
        self.assertEqual(self.session.registration_data.get('agent_pincode'), "380001")

        # 7. Enter experience
        reply = process_message(self.session, "2")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_SEGMENTS)
        self.assertEqual(self.session.registration_data.get('experience_range'), "2-5 years")

        # 8. Enter segments -> Confirmation summary
        reply = process_message(self.session, "1, 2")
        self.assertEqual(self.session.state, WaBotSession.STATE_CONFIRM_DETAILS)
        self.assertIn("Amit Kumar", reply)
        self.assertIn("Registration Summary", reply)

        # 9. Confirm with "yes" -> Advances to Plan Selection!
        reply = process_message(self.session, "yes")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_PLAN)
        self.assertIn("Choose Your Membership Plan", reply)
        self.assertIn("Starter Plan", reply)
        self.assertIn("Professional Plan", reply)

        # 10. Select Plan "1" (Starter) -> Generates Payment Link!
        with patch('apps.wa_agent_bot.services.state_machine.create_plan_payment_link') as mock_link:
            mock_link.return_value = {
                'success': True,
                'payment_link': 'https://rzp.io/i/test1234',
                'payment_link_id': 'plink_test1234',
                'plan_name': 'Starter Plan',
                'base': 1499.0,
                'gst': 269.82,
                'total': 1769,
                'agent': MagicMock(),
                'subscription': MagicMock(),
            }
            reply = process_message(self.session, "1")
            self.assertEqual(self.session.state, WaBotSession.STATE_AWAITING_PAYMENT)
            self.assertIn("Complete Your Registration", reply)
            self.assertIn("https://rzp.io/i/test1234", reply)
            self.assertIn("1769", reply)

    def test_switch_plan_during_awaiting_payment(self):
        self.session.state = WaBotSession.STATE_AWAITING_PAYMENT
        self.session.registration_data = {
            'payment_link': 'https://rzp.io/i/test1234',
            'plan_name': 'Starter Plan',
            'plan_total': 1769,
        }
        reply = process_message(self.session, "change")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_PLAN)
        self.assertIn("Choose Your Membership Plan", reply)

    def test_cancel_command_resets_session(self):
        self.session.state = WaBotSession.STATE_ASK_EMAIL
        self.session.registration_data = {'fullname': 'Amit'}
        reply = process_message(self.session, "cancel")
        self.assertEqual(self.session.state, WaBotSession.STATE_WELCOME)
        self.assertEqual(self.session.registration_data, {})
        self.assertIn("cancelled", reply.lower())

    def test_back_command_navigates_to_previous_state(self):
        self.session.state = WaBotSession.STATE_ASK_PLAN
        reply = process_message(self.session, "back")
        self.assertEqual(self.session.state, WaBotSession.STATE_CONFIRM_DETAILS)


class PostLoginHandlerTests(unittest.TestCase):
    """Test strict boundary enforcement in post-login mode."""

    def setUp(self):
        self.agent = MagicMock()
        self.agent.id = 1001
        self.agent.fullname = "Rajesh Sharma"
        self.agent.email = "rajesh@example.com"
        self.agent.mobile = "9876543210"
        self.agent.agent_id = "AGT-1001"
        self.agent.referral_code = "RAJESH100"
        self.agent.plan_type = "free_trial"
        self.agent.user_types = ["Health", "Life"]
        self.agent.agent_pincode = "380001"
        self.agent.experience_range = "2-5 years"
        self.agent.status = "approved"
        self.agent.average_rating = 4.8
        self.agent.review_count = 12
        self.agent.activeSubscription = None
        self.agent.isOnFreeTrial.return_value = False
        self.agent.isTrialExpired.return_value = False
        self.agent.get_primary_profile.return_value = None

    def test_help_command(self):
        response = process_post_login_message(self.agent, "help")
        self.assertIn("Available Commands", response)
        self.assertIn("profile", response)

    def test_profile_command(self):
        response = process_post_login_message(self.agent, "profile")
        self.assertIn("Rajesh Sharma", response)
        self.assertIn("rajesh@example.com", response)

    def test_dashboard_command(self):
        response = process_post_login_message(self.agent, "dashboard")
        self.assertIn("Dashboard", response)

    def test_referral_command(self):
        response = process_post_login_message(self.agent, "referral")
        self.assertIn("PA001001", response)

    def test_status_command(self):
        response = process_post_login_message(self.agent, "status")
        self.assertIn("Account Status", response)

    def test_support_command(self):
        response = process_post_login_message(self.agent, "support")
        self.assertIn("Support", response)

    def test_out_of_scope_boundary_enforcement(self):
        """User asks anything outside permitted commands -> polite rejection."""
        out_of_bounds_inputs = [
            "book a flight for me",
            "what is the weather today?",
            "delete my account",
            "can you transfer money?",
            "tell me a joke",
            "random message 123",
        ]
        for msg in out_of_bounds_inputs:
            response = process_post_login_message(self.agent, msg)
            self.assertIn("I can only help you with specific commands", response)
            self.assertIn("Type *help*", response)


class WebhookAndPaymentViewTests(unittest.TestCase):
    """Test webhook and payment callback views."""

    def setUp(self):
        self.factory = RequestFactory()

    @patch('apps.wa_agent_bot.views.WaBotSession.objects')
    def test_health_check(self, mock_session_objects):
        mock_session_objects.count.return_value = 5
        mock_session_objects.filter.return_value.count.return_value = 2

        request = self.factory.get('/wa-bot/health/')
        response = views.bot_health(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data.get('status'), 'healthy')
        self.assertEqual(data.get('total_sessions'), 5)
        self.assertEqual(data.get('registered_agents'), 2)

    @patch('apps.agents.models.AgentSubscription.objects')
    def test_payment_callback_renders_html(self, mock_sub_objects):
        mock_sub_objects.filter.return_value.first.return_value = None
        request = self.factory.get('/wa-bot/payment-callback/?razorpay_payment_id=pay_123&razorpay_payment_link_id=plink_123')
        response = views.payment_callback(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn("Payment Successful", content)
        self.assertIn("WhatsApp Credentials Sent", content)

    @patch('apps.agents.models.AgentSubscription.objects')
    @patch('apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment')
    def test_razorpay_webhook_processing(self, mock_activate, mock_sub_objects):
        mock_sub = MagicMock()
        mock_sub.id = 99
        mock_sub_objects.filter.return_value.first.return_value = mock_sub
        mock_activate.return_value = (True, "Activated successfully")

        payload = {
            'event': 'payment_link.paid',
            'payload': {
                'payment_link': {
                    'entity': {
                        'id': 'plink_test999',
                        'notes': {'subscription_id': 99},
                    }
                }
            }
        }
        request = self.factory.post(
            '/wa-bot/razorpay-webhook/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        response = views.razorpay_webhook(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data.get('status'), 'success')

    @patch('apps.home.models.site_setting.SiteSetting.get_value')
    def test_webhook_receiver_when_disabled_via_admin_flag(self, mock_get_val):
        """When Admin Panel flag is OFF (False), webhook receiver responds with status: disabled."""
        mock_get_val.return_value = False
        request = self.factory.post(
            '/wa-bot/webhook/',
            data=json.dumps({'event': 'message:received'}),
            content_type='application/json',
        )
        response = views.webhook_receiver(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data.get('status'), 'disabled')

    @patch('apps.home.models.site_setting.SiteSetting.get_value')
    @patch('apps.wa_agent_bot.views._verify_webhook_signature', return_value=True)
    def test_webhook_receiver_when_enabled_via_admin_flag(self, mock_sig, mock_get_val):
        """When Admin Panel flag is ON (True), webhook receiver proceeds to process request."""
        mock_get_val.return_value = True
        request = self.factory.post(
            '/wa-bot/webhook/',
            data="not-valid-json",
            content_type='application/json',
        )
        response = views.webhook_receiver(request)
        # Should pass the enabled check and fail on JSON parsing
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data.get('error'), 'Invalid JSON')

    @patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=1)
    @patch('apps.home.models.site_setting.SiteSetting.get_value', return_value=True)
    @patch('apps.home.models.site_setting.SiteSetting.set_value')
    @patch('apps.admin_panel.models.admin_activity_log.AdminActivityLog.log')
    def test_admin_toggle_wa_bot_service(self, mock_log, mock_set_val, mock_get_val, mock_admin):
        """Test Admin Panel AJAX endpoint toggles service from True to False and back."""
        from apps.admin_panel.views.settings import toggle_wa_bot_service
        request = self.factory.post('/admin/settings/wa-bot/toggle/')
        response = toggle_wa_bot_service(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode('utf-8'))
        self.assertTrue(data.get('success'))
        self.assertFalse(data.get('enabled'))
        mock_set_val.assert_called_once_with('wa_agent_bot_enabled', False, group='general')
