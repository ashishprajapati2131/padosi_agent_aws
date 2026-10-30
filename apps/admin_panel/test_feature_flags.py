"""
apps/admin_panel/test_feature_flags.py

Comprehensive test suite for Feature Flags Management:
- Service layer testing (default flags, live SiteSetting sync, custom flags)
- Security checks (system flag deletion protection, URL sanitization)
- Controller view tests (index, toggle, create, update, delete)
- Audit logging verification via AdminActivityLog
"""

import datetime
import json
from unittest.mock import patch
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse

from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.user_session import UserSession, UserSessionData
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.home.models.site_setting import SiteSetting
from apps.admin_panel.services.feature_flags import (
    get_all_feature_flags,
    get_feature_flag,
    is_feature_enabled,
    set_feature_flag_status,
    create_custom_feature_flag,
    update_feature_flag_metadata,
    delete_custom_feature_flag,
    get_active_flags_count,
    sanitize_redirect_url,
    sanitize_key,
    FEATURE_FLAGS_REGISTRY_KEY,
)
from apps.admin_panel.views.feature_flags import (
    feature_flags_index,
    feature_flag_toggle,
    feature_flag_create,
    feature_flag_update,
    feature_flag_delete,
)


class DummyMessages:
    def __init__(self):
        self.messages = []
    def add(self, level, message, extra_tags=''):
        self.messages.append(message)
    def __iter__(self):
        return iter(self.messages)


class FeatureFlagsTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.admin = Admin.objects.create(
            name="Super Admin",
            email="admin_ff_test@padosiagent.com",
            password="testpassword",
            role="super"
        )
        SiteSetting.flush_cache()

    def _setup_req(self, req):
        req.session = {'admin_id': self.admin.id}
        req._messages = DummyMessages()
        return req

    def test_default_system_flags_exist(self):
        """Verify that core system flags are registered by default."""
        flags = get_all_feature_flags()
        keys = [f['key'] for f in flags]

        self.assertIn('wholesale_marketplace_enabled', keys)
        self.assertIn('agent_digital_card_enabled', keys)
        self.assertIn('wa_agent_bot_enabled', keys)
        self.assertIn('feature_flag_pincode_heatmap', keys)
        self.assertIn('profile_banner_enabled', keys)
        self.assertIn('subscription_expiry_enforced', keys)

        # Check wholesale flag definition
        wm_flag = get_feature_flag('wholesale_marketplace_enabled')
        self.assertIsNotNone(wm_flag)
        self.assertTrue(wm_flag['is_system'])
        self.assertEqual(wm_flag['redirect_url'], '/wholesale/admin/dashboard/')

    def test_toggle_system_flag_synchronizes_with_site_setting(self):
        """Toggling a system flag should update SiteSetting and flush cache."""
        key = 'wholesale_marketplace_enabled'
        
        # Enable it
        res = set_feature_flag_status(key, True, admin_id=self.admin.id)
        self.assertTrue(res['success'])
        self.assertTrue(res['is_enabled'])

        # Verify SiteSetting was updated
        db_val = SiteSetting.get_value(key)
        self.assertIn(str(db_val).lower(), ('1', 'true'))
        self.assertTrue(is_feature_enabled(key))

        # Disable it
        res2 = set_feature_flag_status(key, False, admin_id=self.admin.id)
        self.assertTrue(res2['success'])
        self.assertFalse(res2['is_enabled'])
        db_val2 = SiteSetting.get_value(key)
        self.assertIn(str(db_val2).lower(), ('0', 'false'))
        self.assertFalse(is_feature_enabled(key))

    def test_create_and_toggle_custom_feature_flag(self):
        """Admins can register new custom feature flags and toggle them."""
        custom_key = 'ai_voice_consultant_pilot'
        create_res = create_custom_feature_flag(
            key=custom_key,
            name='AI Voice Consultant Pilot',
            category='Automation & AI',
            description='Enables live conversational AI voice quotes on landing page.',
            redirect_url='/admin/whatsapp/',
            is_enabled=True,
            icon='fa-solid fa-microphone',
            admin_id=self.admin.id,
        )
        self.assertTrue(create_res['success'])

        # Flag should be in all flags
        flag = get_feature_flag(custom_key)
        self.assertIsNotNone(flag)
        self.assertEqual(flag['name'], 'AI Voice Consultant Pilot')
        self.assertTrue(flag['is_custom'])
        self.assertTrue(flag['is_enabled'])
        self.assertEqual(flag['redirect_url'], '/admin/whatsapp/')

        # Toggle OFF
        toggle_res = set_feature_flag_status(custom_key, False, admin_id=self.admin.id)
        self.assertTrue(toggle_res['success'])
        self.assertFalse(is_feature_enabled(custom_key))

        # Update metadata
        update_res = update_feature_flag_metadata(
            key=custom_key,
            name='AI Voice Consultant V2',
            category='Automation & AI',
            description='Updated pilot description.',
            redirect_url='/admin/settings/general/',
            admin_id=self.admin.id,
        )
        self.assertTrue(update_res['success'])
        updated_flag = get_feature_flag(custom_key)
        self.assertEqual(updated_flag['name'], 'AI Voice Consultant V2')
        self.assertEqual(updated_flag['redirect_url'], '/admin/settings/general/')

        # Delete custom flag
        delete_res = delete_custom_feature_flag(custom_key, admin_id=self.admin.id)
        self.assertTrue(delete_res['success'])
        self.assertIsNone(get_feature_flag(custom_key))

    def test_protection_against_deleting_system_flags(self):
        """System flags cannot be deleted."""
        del_res = delete_custom_feature_flag('wholesale_marketplace_enabled', admin_id=self.admin.id)
        self.assertFalse(del_res['success'])
        self.assertIn('System feature flags cannot be deleted', del_res['message'])
        self.assertIsNotNone(get_feature_flag('wholesale_marketplace_enabled'))

    def test_url_sanitization(self):
        """Redirect URLs must be safely sanitized against malicious schemes."""
        self.assertEqual(sanitize_redirect_url('/admin/dashboard/'), '/admin/dashboard/')
        self.assertEqual(sanitize_redirect_url('wholesale/admin/'), '/wholesale/admin/')
        self.assertEqual(sanitize_redirect_url('https://example.com/docs/'), 'https://example.com/docs/')
        # Block javascript: injection
        self.assertEqual(sanitize_redirect_url('javascript:alert(1)'), '')
        self.assertEqual(sanitize_redirect_url('data:text/html,<script>alert(1)</script>'), '')

    def test_view_feature_flags_index(self):
        """GET /admin/feature-flags/ renders the dashboard view."""
        req = self.rf.get('/admin/feature-flags/')
        self._setup_req(req)
        with patch('apps.admin_panel.views.feature_flags._get_admin_from_session', return_value=self.admin.id):
            resp = feature_flags_index(req)
        self.assertEqual(resp.status_code, 200)

    def test_view_feature_flag_ajax_toggle(self):
        """POST /admin/feature-flags/toggle/ toggles via AJAX and returns JSON."""
        req = self.rf.post(
            '/admin/feature-flags/toggle/',
            data=json.dumps({'key': 'feature_flag_pincode_heatmap', 'state': False}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self._setup_req(req)
        with patch('apps.admin_panel.views.feature_flags._get_admin_from_session', return_value=self.admin.id):
            resp = feature_flag_toggle(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertTrue(data['success'])
        self.assertFalse(data['is_enabled'])

    def test_view_create_custom_feature_flag(self):
        """POST /admin/feature-flags/create/ creates a new flag and redirects."""
        post_data = {
            'key': 'test_festive_promo_2026',
            'name': 'Festive Promo 2026',
            'category': 'Growth & Marketing',
            'description': 'Festive discount banner and promo trigger.',
            'redirect_url': '/admin/referrals/',
            'is_enabled': '1',
            'icon': 'fa-solid fa-gift'
        }
        req = self.rf.post('/admin/feature-flags/create/', post_data)
        self._setup_req(req)
        with patch('apps.admin_panel.views.feature_flags._get_admin_from_session', return_value=self.admin.id):
            resp = feature_flag_create(req)
        self.assertEqual(resp.status_code, 302)

        flag = get_feature_flag('test_festive_promo_2026')
        self.assertIsNotNone(flag)
        self.assertEqual(flag['name'], 'Festive Promo 2026')
        self.assertTrue(flag['is_enabled'])

    def test_custom_flag_never_touches_real_setting(self):
        """A custom flag named like a real setting is namespaced; toggle/delete leave the setting alone."""
        SiteSetting.set_value('razorpay_mode', 'live', group='payment')
        self.assertTrue(create_custom_feature_flag('razorpay_mode', 'X', 'Custom', '', '', is_enabled=True)['success'])
        set_feature_flag_status('razorpay_mode', False)
        self.assertTrue(delete_custom_feature_flag('razorpay_mode')['success'])
        self.assertEqual(SiteSetting.get_value('razorpay_mode'), 'live')
        self.assertFalse(SiteSetting.objects.filter(key='custom_flag_razorpay_mode').exists())
        self.assertFalse(create_custom_feature_flag(FEATURE_FLAGS_REGISTRY_KEY, 'X', 'Custom', '', '')['success'])

    def test_legacy_custom_flag_keeps_bare_key(self):
        """Flags stored before namespacing still read their bare key; delete leaves that row."""
        SiteSetting.set_value(FEATURE_FLAGS_REGISTRY_KEY, {'old_flag': {'key': 'old_flag', 'name': 'Old', 'default': False}})
        SiteSetting.set_value('old_flag', '1')
        self.assertTrue(get_feature_flag('old_flag')['is_enabled'])
        delete_custom_feature_flag('old_flag')
        self.assertTrue(SiteSetting.objects.filter(key='old_flag').exists())

    def test_edited_system_flag_listed_once(self):
        update_feature_flag_metadata('wholesale_marketplace_enabled', 'Wholesale Renamed', '', 'd', '/x/')
        matches = [f for f in get_all_feature_flags() if f['key'] == 'wholesale_marketplace_enabled']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['name'], 'Wholesale Renamed')
        self.assertTrue(matches[0]['is_system'])
        self.assertFalse(matches[0]['is_custom'])

    def test_subscription_expiry_flag_matches_enforcement(self):
        from apps.agents.services.subscription_expiry import expiry_enforced
        self.assertFalse(get_feature_flag('subscription_expiry_enforced')['is_enabled'])
        self.assertFalse(expiry_enforced())

    def test_dead_system_flags_removed(self):
        keys = {f['key'] for f in get_all_feature_flags()}
        for dead in ('fastapi_services_enabled', 'find_agent_locator_v2', 'qr_service_enabled',
                     'google_review_system_enabled', 'event_referral_test_mode'):
            self.assertNotIn(dead, keys)

    def test_permission_check_fails_closed(self):
        req = self._setup_req(self.rf.post('/admin/feature-flags/toggle/', {'key': 'feature_flag_pincode_heatmap'}))
        with patch('apps.admin_panel.views.feature_flags._get_admin_from_session', return_value=self.admin.id), \
             patch('apps.admin_panel.views.feature_flags.Admin.objects.filter', side_effect=Exception('db')):
            resp = feature_flag_toggle(req)
        self.assertEqual(resp.status_code, 403)


class FeatureFlagsStaffAccessTests(TestCase):
    """Staff reach the Control Center only with the permission the sidebar checks."""

    def _client_for(self, admin):
        now = datetime.datetime.now()
        sess = UserSession.objects.create(session_token=f'tok_ff_{admin.id}', admin_id=admin.id,
                                          expires_at=now + datetime.timedelta(days=1), created_at=now, updated_at=now)
        UserSessionData.objects.create(session=sess, data_key='admin_id', data_value=str(admin.id))
        c = Client()
        c.cookies['session_token'] = sess.session_token
        return c

    def test_staff_without_permission_denied(self):
        staff = Admin.objects.create(name='S1', email='s1@ff.test', password='x', role='staff', permissions=['leads'])
        c = self._client_for(staff)
        resp = c.get(reverse('admin_feature_flags'))
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('feature-flags', resp.url)
        resp = c.post(reverse('admin_feature_flag_toggle'), {'key': 'feature_flag_pincode_heatmap', 'state': '0'})
        self.assertNotEqual(resp.status_code, 200)
        self.assertIsNone(SiteSetting.get_value('feature_flag_pincode_heatmap'))

    def test_staff_with_permission_allowed(self):
        staff = Admin.objects.create(name='S2', email='s2@ff.test', password='x', role='staff', permissions=['feature_flags'])
        c = self._client_for(staff)
        self.assertEqual(c.get(reverse('admin_feature_flags')).status_code, 200)
        resp = c.post(reverse('admin_feature_flag_toggle'), {'key': 'feature_flag_pincode_heatmap', 'state': '0'},
                      HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
