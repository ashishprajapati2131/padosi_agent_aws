"""
apps/admin_panel/test_visiting_card_studio.py

Comprehensive test suite for the Admin Panel Personal Digital Visiting Card Studio Management:
1. Studio configuration service & synchronization with master flag
2. Admin Dashboard view & permissions
3. Updating global studio configuration & section policies
4. AJAX 1-click agent card visibility toggle
5. Admin inspection & override API for individual agent cards
6. Resetting agent card to system defaults
7. Effective section policy enforcement on public visiting cards (/card/{slug})
8. Watermark branding toggle enforcement
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models import AdminActivityLog
from apps.home.models import SiteSetting
from apps.agents.models import Agent, AgentProfile, AgentLead
from apps.admin_panel.services.digital_card_studio import (
    get_digital_card_studio_config,
    save_digital_card_studio_config,
    resolve_effective_section_visibility,
)


class VisitingCardStudioAdminTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Super Admin
        self.admin = Admin.objects.create(
            name='Studio Super Admin',
            email='studio_super@test.com',
            password='testpassword',
            role='super'
        )

        # Create Normal Admin without content/agent permissions
        self.limited_admin = Admin.objects.create(
            name='Limited Admin',
            email='limited@test.com',
            password='testpassword',
            role='admin',
            permissions=json.dumps(['broadcast'])
        )

        # Create Test Agent with profile
        self.agent_user = User.objects.create_user(
            username='advisor1@test.com',
            email='advisor1@test.com',
            password='Password123'
        )
        self.agent = Agent.objects.create(
            user=self.agent_user,
            fullname='Vipul Shah',
            email='advisor1@test.com',
            mobile='9825012345',
            status='active'
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug='vipul-shah',
            display_name='Vipul Shah',
            agency_name='Shah Wealth Advisory',
            card_tagline='Guiding 1000+ Happy Families',
            is_card_visible=True,
            card_config={
                'theme_color': '#059669',
                'show_call': True,
                'show_whatsapp': True,
                'show_lead_form': True,
                'show_reviews': False,
            }
        )

        # Ensure feature is enabled by default
        SiteSetting.set_value('agent_digital_card_enabled', True, group='general')

    def _login_admin(self, admin_obj, client=None):
        c = client or self.client
        session = c.session
        session['admin_id'] = admin_obj.id
        session['admin_name'] = admin_obj.name
        session['admin_role'] = admin_obj.role
        session.save()

    def test_default_studio_config_retrieval(self):
        config = get_digital_card_studio_config(use_cache=False)
        self.assertTrue(config.get('enabled'))
        self.assertEqual(config.get('studio_title'), 'Personal Digital Visiting Card Studio')
        self.assertEqual(config.get('policy_call'), 'allow_agent')
        self.assertEqual(config.get('policy_lead_form'), 'allow_agent')
        self.assertTrue(config.get('show_powered_by_badge'))

    def test_save_studio_config_syncs_with_master_flag(self):
        updates = {
            'enabled': False,
            'studio_title': 'Enterprise Digital Visiting Card Hub',
            'policy_lead_form': 'always_hide',
            'show_powered_by_badge': False,
            'default_theme_color': '#4338CA',
        }
        saved = save_digital_card_studio_config(updates)
        self.assertFalse(saved['enabled'])
        self.assertEqual(saved['studio_title'], 'Enterprise Digital Visiting Card Hub')
        self.assertEqual(saved['policy_lead_form'], 'always_hide')
        self.assertFalse(saved['show_powered_by_badge'])
        self.assertEqual(saved['default_theme_color'], '#4338CA')

        # Check SiteSetting synchronization
        master_val = SiteSetting.get_value('agent_digital_card_enabled')
        self.assertIn(str(master_val).strip().lower(), ('0', 'false'))

    def test_admin_studio_index_view_permissions(self):
        url = reverse('admin_digital_card_studio')

        # Unauthenticated -> redirect to login
        res_anon = self.client.get(url)
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn('/login/', res_anon.url)

        # Limited admin without permission -> redirected
        self._login_admin(self.limited_admin)
        res_limited = self.client.get(url)
        self.assertEqual(res_limited.status_code, 302)
        self.assertTrue(res_limited.url.startswith('/admin'))

        # Create a card lead with null enquiry_requirements to verify robust table rendering
        AgentLead.objects.create(
            agent=self.agent,
            customer_name='Ramesh Bhai',
            customer_mobile='9825112233',
            customer_pincode='380015',
            insurance_type='Health',
            interaction_type='digital_card_enquiry',
            enquiry_requirements=None
        )

        # Super admin -> 200 OK with full studio layout & KPIs
        super_client = Client()
        self._login_admin(self.admin, client=super_client)
        res_super = super_client.get(url)
        self.assertEqual(res_super.status_code, 200)
        self.assertContains(res_super, 'Personal Digital Visiting Card Studio')
        self.assertContains(res_super, 'Vipul Shah')
        self.assertContains(res_super, '/card/vipul-shah/')
        self.assertContains(res_super, 'Ramesh Bhai')
        self.assertContains(res_super, 'No note attached.')
        self.assertContains(res_super, 'Global Section Visibility Policies')

    def test_toggle_agent_card_visibility_ajax(self):
        self._login_admin(self.admin)
        url = reverse('admin_digital_card_agent_toggle', kwargs={'agent_id': self.agent.id})

        # Initial status is True
        self.assertTrue(self.profile.is_card_visible)

        # Toggle to False
        res = self.client.post(url)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertFalse(data.get('is_card_visible'))

        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_card_visible)

        # Toggle back to True
        res2 = self.client.post(url)
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertTrue(data2.get('is_card_visible'))

        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_card_visible)

    def test_admin_agent_card_detail_and_save_api(self):
        self._login_admin(self.admin)

        # 1. GET detail
        detail_url = reverse('admin_digital_card_agent_detail', kwargs={'agent_id': self.agent.id})
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, 200)
        data = res_detail.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data['agent']['fullname'], 'Vipul Shah')
        self.assertEqual(data['agent']['theme_color'], '#059669')

        # 2. POST save override
        save_url = reverse('admin_digital_card_agent_save', kwargs={'agent_id': self.agent.id})
        save_payload = {
            'agency_name': 'Shah Financial & Risk Solutions',
            'card_tagline': 'Always Ahead in Policy Claims',
            'theme_color': '#1E293B',
            'banner_style': 'gradient_sunset',
            'custom_button_label': 'Schedule Zoom Call',
            'custom_button_url': 'https://calendly.com/vipul-shah',
            'whatsapp_msg': 'Namaste Vipul Bhai, need claim help.',
            'is_card_visible': '1',
        }
        res_save = self.client.post(save_url, save_payload)
        self.assertEqual(res_save.status_code, 200)
        save_data = res_save.json()
        self.assertTrue(save_data.get('success'))

        # Verify DB updates
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.agency_name, 'Shah Financial & Risk Solutions')
        self.assertEqual(self.profile.card_tagline, 'Always Ahead in Policy Claims')
        cfg = self.profile.get_card_config()
        self.assertEqual(cfg.get('theme_color'), '#1E293B')
        self.assertEqual(cfg.get('banner_style'), 'gradient_sunset')
        self.assertEqual(cfg.get('custom_button_label'), 'Schedule Zoom Call')

    def test_admin_agent_card_reset_to_defaults(self):
        self._login_admin(self.admin)
        save_url = reverse('admin_digital_card_agent_save', kwargs={'agent_id': self.agent.id})

        res_reset = self.client.post(save_url, {'action': 'reset'})
        self.assertEqual(res_reset.status_code, 200)
        data = res_reset.json()
        self.assertTrue(data.get('success'))

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.card_config, {})
        self.assertTrue(self.profile.is_card_visible)

    def test_global_policy_enforcement_on_public_card(self):
        # Even if agent's card_config has show_lead_form = True:
        self.profile.card_config['show_lead_form'] = True
        self.profile.save()

        # Admin sets policy_lead_form = 'always_hide'
        save_digital_card_studio_config({
            'enabled': True,
            'policy_lead_form': 'always_hide',
            'policy_reviews': 'always_show',  # Agent had show_reviews = False, but admin forces ON
        })

        card_url = reverse('agents:agent_public_card', kwargs={'slug': 'vipul-shah'})
        res = self.client.get(card_url)
        self.assertEqual(res.status_code, 200)

        # Lead form must NOT appear because admin policy is always_hide
        self.assertNotContains(res, 'id="enquirySection"')

        # Reviews section MUST appear because admin policy is always_show
        self.assertContains(res, 'Verified Client Reviews')

    def test_watermark_toggle_on_public_card(self):
        # 1. When watermark is enabled (default)
        save_digital_card_studio_config({
            'enabled': True,
            'show_powered_by_badge': True,
            'powered_by_text': 'Powered by PadosiAgent India',
        })
        card_url = reverse('agents:agent_public_card', kwargs={'slug': 'vipul-shah'})
        res_with_watermark = self.client.get(card_url)
        self.assertEqual(res_with_watermark.status_code, 200)
        self.assertContains(res_with_watermark, 'Powered by PadosiAgent India')

        # 2. When admin disables watermark
        save_digital_card_studio_config({
            'enabled': True,
            'show_powered_by_badge': False,
        })
        res_no_watermark = self.client.get(card_url)
        self.assertEqual(res_no_watermark.status_code, 200)
        self.assertNotContains(res_no_watermark, 'Powered by PadosiAgent India')
