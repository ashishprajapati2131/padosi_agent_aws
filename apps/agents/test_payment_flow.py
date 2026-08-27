from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.agents.services.razorpay_checkout import (
    MOCK_SIGNATURE,
    clean_razorpay_credential,
    create_checkout_order,
    is_local_request,
    is_mock_payment,
    razorpay_key_mode,
    sanitize_contact,
    should_mock_razorpay,
)


class RazorpayCheckoutHelperTests(SimpleTestCase):
    def test_sanitize_contact_strips_country_code(self):
        self.assertEqual(sanitize_contact('+91 98765 43210'), '9876543210')
        self.assertEqual(sanitize_contact('09876543210'), '9876543210')
        self.assertEqual(sanitize_contact('not-a-phone'), '')

    def test_clean_razorpay_credential_strips_quotes_and_whitespace(self):
        self.assertEqual(clean_razorpay_credential('  "rzp_live_abc"  '), 'rzp_live_abc')
        self.assertEqual(clean_razorpay_credential("'rzp_test_xyz'"), 'rzp_test_xyz')

    def test_mock_payment_only_in_debug(self):
        with override_settings(DEBUG=True):
            self.assertTrue(is_mock_payment('order_local_123', ''))
            self.assertTrue(is_mock_payment('order_xyz', MOCK_SIGNATURE))
        with override_settings(DEBUG=False):
            self.assertFalse(is_mock_payment('order_local_123', MOCK_SIGNATURE))

    @override_settings(DEBUG=True, RAZORPAY_KEY='', RAZORPAY_SECRET='')
    def test_missing_keys_mock_in_debug(self):
        request = RequestFactory().get('/', HTTP_HOST='127.0.0.1:1234')
        self.assertEqual(razorpay_key_mode(), 'missing')
        self.assertTrue(should_mock_razorpay(request))

    @override_settings(DEBUG=True, RAZORPAY_KEY='rzp_live_abc', RAZORPAY_SECRET='secret')
    def test_live_keys_on_localhost_are_mocked(self):
        request = RequestFactory().get('/', HTTP_HOST='127.0.0.1:1234')
        self.assertTrue(is_local_request(request))
        self.assertTrue(should_mock_razorpay(request))

    @override_settings(DEBUG=True, RAZORPAY_KEY='rzp_test_abc', RAZORPAY_SECRET='secret')
    def test_test_keys_are_not_mocked(self):
        request = RequestFactory().get('/', HTTP_HOST='127.0.0.1:1234')
        self.assertFalse(should_mock_razorpay(request))

    @override_settings(DEBUG=False, RAZORPAY_KEY='', RAZORPAY_SECRET='')
    def test_production_never_mocks(self):
        request = RequestFactory().get('/', HTTP_HOST='127.0.0.1:1234')
        self.assertFalse(should_mock_razorpay(request))

    @override_settings(DEBUG=True, RAZORPAY_KEY='', RAZORPAY_SECRET='')
    def test_create_order_returns_local_mock(self):
        request = RequestFactory().get('/', HTTP_HOST='127.0.0.1:1234')
        order_id, is_mock = create_checkout_order(153300, 'agent_draft_1', request)
        self.assertTrue(is_mock)
        self.assertTrue(order_id.startswith('order_local_'))


class StarterPlanPricingTests(SimpleTestCase):
    def setUp(self):
        self.pricing = {
            'starter': {
                'name': "Starter's Plan",
                'full_price': 1999,
                'promo_price': 1499,
                'scratch_price': 499,
                'scratch_enabled': True,
            },
            'professional': {
                'name': "Professional's Plan",
                'full_price': 6999,
                'promo_price': 4999,
                'scratch_price': 3999,
                'scratch_enabled': True,
            },
            'social_discount_active': False,
        }

    def test_without_scratch_charges_full_plus_gst(self):
        from apps.agents.views.registration import _gst_bundle_from_base, _plan_payable_total
        expected = _gst_bundle_from_base(1999)[2]
        self.assertEqual(expected, 2359)
        charged = _plan_payable_total(self.pricing, 0, 'starter', scratch_revealed=False)
        self.assertEqual(charged, expected)

    def test_after_scratch_charges_scratch_plus_gst(self):
        from apps.agents.views.registration import _gst_bundle_from_base, _plan_payable_total
        expected = _gst_bundle_from_base(499)[2]
        charged = _plan_payable_total(self.pricing, 0, 'starter', scratch_revealed=True)
        self.assertEqual(charged, expected)
        self.assertLess(charged, 2359)

    def test_professional_without_scratch_charges_full_plus_gst(self):
        from apps.agents.views.registration import _gst_bundle_from_base, _plan_payable_total
        expected = _gst_bundle_from_base(6999)[2]
        charged = _plan_payable_total(self.pricing, 0, 'professional', scratch_revealed=False)
        self.assertEqual(charged, expected)

    def test_stale_session_does_not_undercharge_when_summary_shows_full(self):
        from apps.agents.views.registration import _checkout_total_for_plan
        request = RequestFactory().post('/agent-register/complete/')
        request.session = {'scratch_revealed_starter': True}
        data = {'scratch_revealed': False, 'displayed_total': 2359}
        charged = _checkout_total_for_plan(self.pricing, 0, 'starter', request, data)
        self.assertEqual(charged, 2359)

    def test_summary_full_total_overrides_client_reveal_flag(self):
        from apps.agents.views.registration import _checkout_total_for_plan
        request = RequestFactory().post('/agent-register/complete/')
        request.session = {'scratch_revealed_starter': True}
        data = {'scratch_revealed': True, 'displayed_total': 2359}
        charged = _checkout_total_for_plan(self.pricing, 0, 'starter', request, data)
        self.assertEqual(charged, 2359)

    def test_actual_scratch_reveal_charges_summary_total(self):
        from apps.agents.views.registration import _checkout_total_for_plan, _gst_bundle_from_base
        expected = _gst_bundle_from_base(499)[2]
        request = RequestFactory().post('/agent-register/complete/')
        request.session = {'scratch_revealed_starter': True}
        data = {'scratch_revealed': True, 'displayed_total': expected}
        charged = _checkout_total_for_plan(self.pricing, 0, 'starter', request, data)
        self.assertEqual(charged, expected)

    def test_professional_checkout_matches_full_summary(self):
        from apps.agents.views.registration import _checkout_total_for_plan, _gst_bundle_from_base
        expected = _gst_bundle_from_base(6999)[2]
        request = RequestFactory().post('/agent-register/complete/')
        request.session = {}
        data = {'scratch_revealed': False, 'displayed_total': expected}
        charged = _checkout_total_for_plan(self.pricing, 0, 'professional', request, data)
        self.assertEqual(charged, expected)


class RazorpayVerifyFlowTests(SimpleTestCase):
    def test_netbanking_auth_step_is_not_terminal_failure(self):
        from apps.agents.views.registration import _is_in_progress_razorpay_error
        self.assertTrue(_is_in_progress_razorpay_error({
            'step': 'payment_authentication',
            'reason': 'payment_failed',
        }))
        self.assertFalse(_is_in_progress_razorpay_error({
            'step': 'payment_authorization',
            'reason': 'payment_failed',
        }))

    def test_paise_amounts_allow_one_rupee_gst_rounding(self):
        from apps.agents.views.registration import _paise_amounts_match
        self.assertTrue(_paise_amounts_match(58800, 58900))
        self.assertFalse(_paise_amounts_match(58800, 235900))
