import json
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.admin_panel.views import settings, pincode_heatmap
from apps.home.views import pages
from apps.home.models.site_setting import SiteSetting


class DummyMessages:
    def add(self, *args, **kwargs): pass
    def __iter__(self): return iter([])


class BannerPopupAndHeatmapTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.admin = Admin.objects.create(
            name="Super Admin",
            email="admin_banner_test@padosiagent.com",
            password="testpassword",
            role="super"
        )

    def _setup_req(self, req):
        req.session = {'admin_id': self.admin.id}
        req._messages = DummyMessages()
        return req

    def test_quick_lead_capture(self):
        req = self.rf.post('/api/quick-lead-capture/', {
            'name': 'Pooja Patel',
            'mobile': '9876543210',
            'pincode': '380015',
            'insurance_type': 'Health Insurance'
        })
        resp = pages.quick_lead_capture(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertEqual(data['status'], 'success')

        lead = ContactSubmission.objects.filter(mobile='9876543210').first()
        self.assertIsNotNone(lead)
        self.assertEqual(lead.name, 'Pooja Patel')
        self.assertIn('Exit-Intent Popup', lead.message)

    def test_save_banner_settings(self):
        req = self.rf.post('/admin/settings/banner-popup/save-banner/', {
            'is_active': '1',
            'message': 'Diwali Offer Live!',
            'btn_text': 'Get Offer',
            'btn_url': '/find-agents/',
            'theme': 'emerald',
            'bg_color': '#059669',
            'text_color': '#ffffff',
            'is_dismissible': '1',
            'target_page': 'all'
        })
        self._setup_req(req)
        with patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=self.admin.pk):
            resp = settings.save_banner_settings(req)
        self.assertEqual(resp.status_code, 302)

        banner = SiteSetting.get_value('site_announcement_banner')
        self.assertTrue(banner['is_active'])
        self.assertEqual(banner['message'], 'Diwali Offer Live!')

    def test_save_popup_settings(self):
        req = self.rf.post('/admin/settings/banner-popup/save-popup/', {
            'is_active': '1',
            'popup_type': 'lead_form',
            'eyebrow': 'WAIT',
            'title': 'Free Consultation',
            'description': 'Connect with local advisor',
            'btn_text': 'Submit',
            'timer_seconds': '20',
            'dismiss_days': '5',
            'target_page': 'all'
        })
        self._setup_req(req)
        with patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=self.admin.pk):
            resp = settings.save_popup_settings(req)
        self.assertEqual(resp.status_code, 302)

        popup = SiteSetting.get_value('site_exit_popup')
        self.assertTrue(popup['is_active'])
        self.assertEqual(popup['timer_seconds'], 20)

    def test_heatmap_view_and_feature_flag(self):
        req = self.rf.get('/admin/pincode-heatmap/')
        self._setup_req(req)
        with patch('apps.admin_panel.views.pincode_heatmap._get_admin_from_session', return_value=self.admin.pk):
            resp = pincode_heatmap.pincode_heatmap_index(req)
        self.assertEqual(resp.status_code, 200)

        # Toggle flag
        post_req = self.rf.post('/admin/pincode-heatmap/toggle-flag/')
        self._setup_req(post_req)
        with patch('apps.admin_panel.views.pincode_heatmap._get_admin_from_session', return_value=self.admin.pk):
            resp_toggle = pincode_heatmap.toggle_heatmap_flag(post_req)
        self.assertEqual(resp_toggle.status_code, 302)
