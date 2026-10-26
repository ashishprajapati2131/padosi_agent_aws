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

import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch
from django.test import RequestFactory, override_settings

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

    def test_parse_contact_input(self):
        # Combined mobile + email
        res = validators.parse_contact_input("6352701899parthsadhu0309@gmail.com")
        self.assertEqual(res['mobile'], "6352701899")
        self.assertEqual(res['email'], "parthsadhu0309@gmail.com")

        # Reverse concatenated email + mobile
        res = validators.parse_contact_input("parthsadhu0309@gmail.com6352701899")
        self.assertEqual(res['mobile'], "6352701899")
        self.assertEqual(res['email'], "parthsadhu0309@gmail.com")

        # Separated with space
        res = validators.parse_contact_input("6352701899 parthsadhu0309@gmail.com")
        self.assertEqual(res['mobile'], "6352701899")
        self.assertEqual(res['email'], "parthsadhu0309@gmail.com")

        # Only mobile
        res = validators.parse_contact_input("6352701899")
        self.assertEqual(res['mobile'], "6352701899")
        self.assertIsNone(res['email'])

        # Only email
        res = validators.parse_contact_input("parthsadhu0309@gmail.com")
        self.assertIsNone(res['mobile'])
        self.assertEqual(res['email'], "parthsadhu0309@gmail.com")

    def test_validate_state(self):
        valid, val = validators.validate_state_selection("1")
        self.assertTrue(valid)
        self.assertEqual(val, "Andhra Pradesh")

        valid, val = validators.validate_state_selection("Maharashtra")
        self.assertTrue(valid)
        self.assertEqual(val, "Maharashtra")

        # Abbreviations & cities
        valid, val = validators.validate_state_selection("GJ")
        self.assertTrue(valid)
        self.assertEqual(val, "Gujarat")

        valid, val = validators.validate_state_selection("mumbai")
        self.assertTrue(valid)
        self.assertEqual(val, "Maharashtra")

        valid, err = validators.validate_state_selection("InvalidState123")
        self.assertFalse(valid)

    def test_validate_pincode(self):
        valid, val = validators.validate_pincode("380001")
        self.assertTrue(valid)
        self.assertEqual(val, "380001")

        # Pincode embedded in text
        valid, val = validators.validate_pincode("380015 Ahmedabad")
        self.assertTrue(valid)
        self.assertEqual(val, "380015")

        valid, err = validators.validate_pincode("1234")
        self.assertFalse(valid)

    def test_validate_experience(self):
        valid, val = validators.validate_experience_selection("2")
        self.assertTrue(valid)
        self.assertEqual(val, "2-5 years")

        # Natural language and years
        valid, val = validators.validate_experience_selection("fresher")
        self.assertTrue(valid)
        self.assertEqual(val, "0-2 years")

        valid, val = validators.validate_experience_selection("3 years")
        self.assertTrue(valid)
        self.assertEqual(val, "2-5 years")

        valid, val = validators.validate_experience_selection("15 years")
        self.assertTrue(valid)
        self.assertEqual(val, "10+ years")

        valid, err = validators.validate_experience_selection("invalid-choice")
        self.assertFalse(valid)

    def test_validate_segments(self):
        valid, val = validators.validate_segments_selection("1, 3")
        self.assertTrue(valid)
        self.assertIn("health", val)
        self.assertIn("motor", val)

        # 'and' noise words
        valid, val = validators.validate_segments_selection("1 and 2")
        self.assertTrue(valid)
        self.assertEqual(val, ["health", "life"])

        # Compact digits
        valid, val = validators.validate_segments_selection("1234")
        self.assertTrue(valid)
        self.assertEqual(len(val), 4)

        # 'all' / 'badha'
        valid, val = validators.validate_segments_selection("all")
        self.assertTrue(valid)
        self.assertEqual(len(val), 4)


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
        # Built-in defaults only: settings cached by another test in the same (parallel) worker must not leak in.
        settings_patch = patch('apps.home.models.site_setting.SiteSetting.get_value', side_effect=lambda key, default=None: default)
        settings_patch.start()
        self.addCleanup(settings_patch.stop)

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
        self.assertIn("Digital Presence", reply)
        self.assertIn("Professional Presence", reply)
        self.assertNotIn("30-Day Trial", reply)

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

    @patch('apps.agents.models.Agent.objects')
    def test_registration_with_combined_email_and_mobile(self, mock_agent_objects):
        mock_agent_objects.filter.return_value.exists.return_value = False
        self.session.state = WaBotSession.STATE_ASK_EMAIL
        self.session.registration_data = {'fullname': 'Parth Sadhu'}

        reply = process_message(self.session, "6352701899parthsadhu0309@gmail.com")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_STATE)
        self.assertEqual(self.session.registration_data.get('email'), "parthsadhu0309@gmail.com")
        self.assertEqual(self.session.registration_data.get('mobile'), "6352701899")
        self.assertIn("Email & Mobile Saved", reply)
        self.assertIn("Step 4 of 7", reply)

    @patch('apps.agents.models.Agent.objects')
    def test_registration_mobile_entered_at_email_step(self, mock_agent_objects):
        mock_agent_objects.filter.return_value.exists.return_value = False
        self.session.state = WaBotSession.STATE_ASK_EMAIL
        self.session.registration_data = {'fullname': 'Parth Sadhu'}

        # 1. User accidentally enters mobile number at email step
        reply = process_message(self.session, "6352701899")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_EMAIL)
        self.assertEqual(self.session.registration_data.get('mobile'), "6352701899")
        self.assertIn("Got your mobile number", reply)

        # 2. User then enters email address
        reply2 = process_message(self.session, "parthsadhu0309@gmail.com")
        # Should skip asking for mobile again and jump straight to state selection
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_STATE)
        self.assertEqual(self.session.registration_data.get('email'), "parthsadhu0309@gmail.com")
        self.assertEqual(self.session.registration_data.get('mobile'), "6352701899")
        self.assertIn("Step 4 of 7", reply2)

    @patch('apps.agents.models.Agent.objects')
    def test_registration_quick_whatsapp_number(self, mock_agent_objects):
        mock_agent_objects.filter.return_value.exists.return_value = False
        self.session.phone_number = "916352701839"
        self.session.state = WaBotSession.STATE_ASK_MOBILE
        self.session.registration_data = {'fullname': 'Parth Sadhu', 'email': 'parthsadhu0309@gmail.com'}

        reply = process_message(self.session, "yes")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_STATE)
        self.assertEqual(self.session.registration_data.get('mobile'), "6352701839")
        self.assertIn("Step 4 of 7", reply)


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
        self.assertIn("Payment Received", content)
        self.assertIn("WhatsApp & Email", content)

    @patch('apps.agents.services.razorpay_checkout.razorpay_webhook_secret', return_value='whsec_test')
    @patch('apps.agents.models.AgentSubscription.objects')
    @patch('apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment')
    def test_razorpay_webhook_processing(self, mock_activate, mock_sub_objects, _mock_secret):
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
        body = json.dumps(payload)
        request = self.factory.post(
            '/wa-bot/razorpay-webhook/',
            data=body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=hmac.new(b'whsec_test', body.encode(), hashlib.sha256).hexdigest(),
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
        mock_set_val.assert_called_once_with('wa_agent_bot_enabled', '0', group='general')

    def test_post_login_status_and_card_reflects_pending_approval(self):
        """Test post-login handler formats status as Pending Admin Approval and informs agent."""
        from apps.wa_agent_bot.services.post_login_handler import handle_status, handle_card
        agent = MagicMock()
        agent.fullname = "Kishor Shah"
        agent.email = "kishor@example.com"
        agent.mobile = "9825123456"
        agent.plan_type = "digital"
        agent.average_rating = 5.0
        agent.review_count = 0
        agent.activeSubscription = None
        agent.get_primary_profile.return_value = None
        agent.id = 101

        # While pending approval
        agent.status = 'pending_approval'
        status_resp = handle_status(agent)
        self.assertIn("Pending Admin Approval", status_resp)
        self.assertIn("under review", status_resp.lower())

        card_resp = handle_card(agent)
        self.assertIn("Pending Admin Approval", card_resp)
        self.assertIn("/card/101/", card_resp)

        # After approval
        agent.status = 'active'
        active_status = handle_status(agent)
        self.assertIn("Active & Verified", active_status)

        active_card = handle_card(agent)
        self.assertIn("Active & Live", active_card)

    @patch('apps.wa_agent_bot.models.WaBotSession.objects')
    @patch('apps.wa_agent_bot.services.message_sender.send_text_message')
    @patch('apps.wa_agent_bot.views.is_wa_bot_enabled', return_value=True)
    def test_notify_agent_approved_whatsapp(self, mock_enabled, mock_send, mock_session_objects):
        """Test approval notification helper dispatches WhatsApp message with live links."""
        from apps.wa_agent_bot.services.notification_service import notify_agent_approved_whatsapp
        from apps.agents.models import Agent
        mock_send.return_value = {'success': True}
        mock_session_objects.filter.return_value.first.return_value = None

        with patch('apps.agents.models.Agent.objects.filter') as mock_agent_filter:
            mock_agent = MagicMock()
            mock_agent.id = 88
            mock_agent.fullname = "Rajesh Mehta"
            mock_agent.mobile = "9825000000"
            mock_agent.get_primary_profile.return_value = None
            mock_agent_filter.return_value.first.return_value = mock_agent

            success, msg = notify_agent_approved_whatsapp(88)
            self.assertTrue(success)
            self.assertEqual(msg, "Notification sent")
            mock_send.assert_called_once()
            called_phone = mock_send.call_args[0][0]
            called_text = mock_send.call_args[0][1]
            self.assertEqual(called_phone, "919825000000")
            self.assertIn("APPROVED", called_text)
            self.assertIn("/profile/88/", called_text)
            self.assertIn("/card/88/", called_text)


class BotSecurityTests(unittest.TestCase):
    """Regression tests for the 2026-10-26 security fixes (C3, C4, C5, H1)."""

    def setUp(self):
        self.factory = RequestFactory()

    @patch('apps.agents.services.razorpay_checkout.razorpay_webhook_secret', return_value='whsec_test')
    @patch('apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment')
    def test_razorpay_webhook_rejects_unsigned(self, mock_activate, _mock_secret):
        body = json.dumps({'payload': {'payment': {'entity': {'notes': {'subscription_id': 1}}}}})
        request = self.factory.post('/wa-bot/razorpay-webhook/', data=body, content_type='application/json')
        response = views.razorpay_webhook(request)
        self.assertEqual(response.status_code, 400)
        mock_activate.assert_not_called()

    @patch('apps.agents.services.razorpay_checkout.razorpay_client')
    @patch('apps.agents.models.AgentSubscription.objects')
    @patch('apps.wa_agent_bot.services.payment_service.activate_agent_subscription_after_payment')
    def test_payment_callback_test_prefix_does_not_activate(self, mock_activate, mock_sub_objects, mock_client):
        sub = MagicMock(payment_status='pending', razorpay_order_id='plink_X', selected_plan='starter')
        sub.agent.email = 'victim@example.com'
        mock_sub_objects.filter.return_value.first.return_value = sub
        mock_client.return_value.payment_link.fetch.return_value = {'status': 'created'}
        request = self.factory.get('/wa-bot/payment-callback/?razorpay_payment_link_id=plink_X&razorpay_payment_id=pay_test_1')
        response = views.payment_callback(request)
        mock_activate.assert_not_called()
        self.assertNotIn('victim@example.com', response.content.decode('utf-8'))

    @override_settings(DEBUG=False)
    def test_inbound_webhook_fails_closed_without_secret(self):
        request = self.factory.post('/wa-bot/webhook/', data='{}', content_type='application/json')
        with patch.dict('os.environ', {'WA_BOT_WEBHOOK_SECRET': ''}):
            self.assertFalse(views._verify_webhook_signature(request))

    def test_inbound_webhook_token(self):
        with patch.dict('os.environ', {'WA_BOT_WEBHOOK_SECRET': 's3cret'}):
            ok = self.factory.post('/wa-bot/webhook/?token=s3cret', data='{}', content_type='application/json')
            bad = self.factory.post('/wa-bot/webhook/?token=nope', data='{}', content_type='application/json')
            self.assertTrue(views._verify_webhook_signature(ok))
            self.assertFalse(views._verify_webhook_signature(bad))

    @patch('apps.admin_panel.views.dashboard._get_admin_from_session', return_value=None)
    def test_simulator_requires_admin(self, _mock_admin):
        from apps.wa_agent_bot import simulator_views
        request = self.factory.post('/wa-bot/simulator/simulate-payment/', data='{}', content_type='application/json')
        request._dont_enforce_csrf_checks = True
        self.assertEqual(simulator_views.simulator_payment(request).status_code, 403)

    @patch('apps.agents.services.account_auth.email_owned_by_non_agent_account', return_value=False)
    @patch('apps.wa_agent_bot.services.registration_handler.User')
    @patch('apps.agents.models.Agent.objects')
    def test_registration_never_takes_over_existing_login(self, mock_agents, mock_user, _mock_owned):
        """Finding #1: an email that already has an auth_user must be rejected, not have its password reset."""
        from apps.wa_agent_bot.services.registration_handler import create_agent_from_wa_data
        mock_agents.filter.return_value.exists.return_value = False
        mock_user.objects.filter.return_value.exists.return_value = True
        result = create_agent_from_wa_data({'email': 'admin@example.com', 'fullname': 'X Y', 'mobile': '9800000000'})
        self.assertFalse(result['success'])
        mock_user.objects.create_user.assert_not_called()
        mock_user.objects.get.assert_not_called()

    def test_openwa_override_url_blocks_internal_hosts(self):
        """Finding #8: admin-typed OpenWA URL can't reach metadata/internal hosts."""
        from apps.wa_agent_bot.services.openwa_admin_service import _override_url_allowed
        configured = 'http://localhost:2785'
        self.assertFalse(_override_url_allowed('http://169.254.169.254/latest/meta-data', configured))
        self.assertFalse(_override_url_allowed('http://10.0.0.5:8080', configured))
        self.assertFalse(_override_url_allowed('file:///etc/passwd', configured))
        self.assertTrue(_override_url_allowed('http://localhost:2785/api', configured))

    @patch('apps.agents.services.account_auth.email_owned_by_non_agent_account', return_value=False)
    @patch('apps.wa_agent_bot.services.registration_handler.User')
    @patch('apps.agents.models.Agent.objects')
    def test_registration_never_takes_over_existing_login(self, mock_agents, mock_user, _mock_owned):
        """Finding #1: an email that already has an auth_user must be rejected, not have its password reset."""
        from apps.wa_agent_bot.services.registration_handler import create_agent_from_wa_data
        mock_agents.filter.return_value.exists.return_value = False
        mock_user.objects.filter.return_value.exists.return_value = True
        result = create_agent_from_wa_data({'email': 'admin@example.com', 'fullname': 'X Y', 'mobile': '9800000000'})
        self.assertFalse(result['success'])
        mock_user.objects.create_user.assert_not_called()
        mock_user.objects.get.assert_not_called()

    def test_openwa_override_url_blocks_internal_hosts(self):
        """Finding #8: admin-typed OpenWA URL can't reach metadata/internal hosts."""
        from apps.wa_agent_bot.services.openwa_admin_service import _override_url_allowed
        configured = 'http://localhost:2785'
        self.assertFalse(_override_url_allowed('http://169.254.169.254/latest/meta-data', configured))
        self.assertFalse(_override_url_allowed('http://10.0.0.5:8080', configured))
        self.assertFalse(_override_url_allowed('file:///etc/passwd', configured))
        self.assertTrue(_override_url_allowed('http://localhost:2785/api', configured))


class LeadAlertTests(unittest.TestCase):
    """WhatsApp message to the agent on a new lead, behind the wa_lead_alert_enabled flag."""

    def _lead(self):
        lead = MagicMock(id=7, customer_name='Ramesh', customer_mobile='9811111111', customer_email='',
                         insurance_type='Health', service_type='', customer_pincode='380001',
                         enquiry_requirements='Family floater')
        lead.agent.mobile = '98250 00000'
        return lead

    @patch('apps.wa_agent_bot.services.message_sender.send_text_message')
    @patch('apps.wa_agent_bot.services.notification_service.lead_alerts_enabled', return_value=False)
    def test_flag_off_sends_nothing(self, _flag, mock_send):
        from apps.wa_agent_bot.services.notification_service import notify_agent_new_lead
        self.assertFalse(notify_agent_new_lead(self._lead()))
        mock_send.assert_not_called()

    @patch('threading.Thread')
    @patch('apps.wa_agent_bot.services.message_sender.send_text_message', return_value={'success': True})
    @patch('apps.wa_agent_bot.services.notification_service.lead_alerts_enabled', return_value=True)
    def test_flag_on_messages_agent(self, _flag, mock_send, mock_thread):
        from apps.wa_agent_bot.services.notification_service import notify_agent_new_lead
        mock_thread.side_effect = lambda target, daemon: MagicMock(start=target)
        self.assertTrue(notify_agent_new_lead(self._lead()))
        phone, text = mock_send.call_args[0]
        self.assertEqual(phone, '919825000000')
        self.assertIn('Ramesh', text)
        self.assertIn('9811111111', text)

    @patch('apps.wa_agent_bot.services.message_sender.send_text_message')
    @patch('apps.wa_agent_bot.services.notification_service.lead_alerts_enabled', return_value=True)
    def test_agent_without_mobile_is_skipped(self, _flag, mock_send):
        from apps.wa_agent_bot.services.notification_service import notify_agent_new_lead
        lead = self._lead()
        lead.agent.mobile = ''
        self.assertFalse(notify_agent_new_lead(lead))
        mock_send.assert_not_called()


class SiteUrlTests(unittest.TestCase):
    @override_settings(DEBUG=False, APP_URL='https://padosiagent.com')
    def test_localhost_site_url_is_ignored_in_production(self):
        from apps.wa_agent_bot.services.site_url import bot_site_url
        with patch.dict('os.environ', {'WA_BOT_SITE_URL': 'http://localhost:8000'}):
            self.assertEqual(bot_site_url(), 'https://padosiagent.com')

    @override_settings(DEBUG=False, APP_URL='')
    def test_falls_back_to_canonical_origin(self):
        from apps.wa_agent_bot.services.site_url import bot_site_url
        with patch.dict('os.environ', {'WA_BOT_SITE_URL': 'http://127.0.0.1:8000'}):
            self.assertEqual(bot_site_url(), 'https://padosiagent.com')


GET_VALUE = 'apps.home.models.site_setting.SiteSetting.get_value'


class MessageTemplateTests(unittest.TestCase):
    def _settings(self, templates=None, keywords=None):
        values = {'wa_message_templates': templates or {}, 'wa_keyword_replies': keywords or []}
        return patch(GET_VALUE, side_effect=lambda key, default=None: values.get(key, default))

    def test_default_drops_lines_with_empty_values(self):
        from apps.wa_agent_bot.services.message_templates import render
        with self._settings():
            text = render('lead_alert', customer_name='Ramesh', customer_mobile='98', customer_email='',
                          dashboard_url='https://x/agent/dashboard/')
        self.assertIn('Ramesh', text)
        self.assertNotIn('Email', text)
        self.assertNotIn('Pincode', text)

    def test_admin_override_is_used(self):
        from apps.wa_agent_bot.services.message_templates import render
        with self._settings({'approval': 'Hi {agent_name}! {card_url}'}):
            self.assertEqual(render('approval', agent_name='Asha', card_url='https://c'), 'Hi Asha! https://c')

    def test_broken_override_falls_back_to_default(self):
        from apps.wa_agent_bot.services.message_templates import render
        with self._settings({'approval': 'Hi {agent_name.upper}'}):
            self.assertIn('Congratulations, Asha', render('approval', agent_name='Asha'))

    def test_template_errors(self):
        from apps.wa_agent_bot.services.message_templates import template_errors
        self.assertEqual(template_errors('approval', 'Hi {agent_name}'), [])
        self.assertTrue(template_errors('approval', 'Hi {password}'))
        self.assertTrue(template_errors('approval', 'Hi {agent_name'))

    def test_keyword_matching(self):
        from apps.wa_agent_bot.services.message_templates import match_keyword_reply
        rules = [
            {'keyword': 'Price', 'reply': 'Plans start at 999', 'match': 'exact', 'active': True},
            {'keyword': 'office', 'reply': 'We are in Ahmedabad', 'match': 'contains', 'active': True},
            {'keyword': 'off', 'reply': 'never', 'match': 'exact', 'active': False},
        ]
        with self._settings(keywords=rules):
            self.assertEqual(match_keyword_reply('  price '), 'Plans start at 999')
            self.assertIsNone(match_keyword_reply('price list'))
            self.assertEqual(match_keyword_reply('where is your office?'), 'We are in Ahmedabad')
            self.assertIsNone(match_keyword_reply('off'))

    def test_keyword_reply_only_outside_registration(self):
        rules = [{'keyword': 'price', 'reply': 'Plans start at 999', 'match': 'exact', 'active': True}]
        with self._settings(keywords=rules):
            welcome = MagicMock(state=WaBotSession.STATE_WELCOME, is_logged_in=False, agent=None)
            self.assertEqual(process_message(welcome, 'price'), 'Plans start at 999')
            mid = MagicMock(state=WaBotSession.STATE_ASK_FULLNAME, is_logged_in=False, agent=None, registration_data={})
            self.assertNotEqual(process_message(mid, 'price'), 'Plans start at 999')
