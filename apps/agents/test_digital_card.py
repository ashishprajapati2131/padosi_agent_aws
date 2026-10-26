from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.agents.models import Agent, AgentProfile, AgentLead, AgentSubscription
from apps.home.models import SiteSetting


class AgentDigitalCardTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='cardagent@test.com',
            email='cardagent@test.com',
            password='Password123'
        )
        self.agent = Agent.objects.create(
            user=self.user,
            fullname='Kishan Patel',
            email='cardagent@test.com',
            mobile='9876543210',
            status='active',
            plan_type='professional'
        )
        self.profile = AgentProfile.objects.create(
            agent=self.agent,
            slug='kishan-patel',
            display_name='Kishan Patel',
            whatsapp='9876543210',
            agency_name='Patel Insurance Care',
            license_number='IRDAI12345678',
            experience_years=8,
            languages='Gujarati, Hindi, English',
            is_profile_visible=True,
            is_card_visible=True
        )
        AgentSubscription.objects.create(
            agent=self.agent,
            selected_plan="Professional Plan",
            registration_amount=2999,
            payment_status='completed',
            status='active',
            razorpay_order_id='order_TESTCARD123',
            razorpay_payment_id='pay_TESTCARD123',
        )
        SiteSetting.set_value('agent_digital_card_enabled', True, group='general')

    def test_public_card_page_renders_successfully(self):
        url = reverse('agents:agent_public_card', kwargs={'slug': 'kishan-patel'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kishan Patel')
        self.assertContains(response, 'Patel Insurance Care')
        self.assertContains(response, 'Save Contact')
        self.assertContains(response, 'Get in Touch')

    def test_vcard_download_returns_valid_vcf(self):
        url = reverse('agents:agent_card_vcf', kwargs={'slug': 'kishan-patel'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/vcard; charset=utf-8')
        self.assertIn('attachment; filename="PadosiAgent-kishan-patel.vcf"', response['Content-Disposition'])
        content = response.content.decode('utf-8')
        self.assertIn('BEGIN:VCARD', content)
        self.assertIn('FN;CHARSET=UTF-8:Kishan Patel', content)
        self.assertIn('TEL;TYPE=CELL,VOICE;CHARSET=UTF-8:9876543210', content)
        self.assertIn('END:VCARD', content)

    def test_lead_submission_creates_agent_lead(self):
        url = reverse('agents:agent_card_lead_submit', kwargs={'slug': 'kishan-patel'})
        data = {
            'customer_name': 'Ramesh Bhai',
            'customer_mobile': '9898989898',
            'customer_pincode': '380015',
            'insurance_type': 'Health Insurance',
            'service_type': 'New Policy Purchase',
            'message': 'Family floater plan requred for 4 members'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get('success'))

        # Verify database record
        lead = AgentLead.objects.filter(agent=self.agent, customer_mobile='9898989898').first()
        self.assertIsNotNone(lead)
        self.assertEqual(lead.customer_name, 'Ramesh Bhai')
        self.assertEqual(lead.insurance_type, 'Health Insurance')
        self.assertEqual(lead.service_type, 'New Policy Purchase')
        self.assertEqual(lead.interaction_type, 'digital_card_enquiry')
        self.assertEqual(lead.source_page, 'digital-card')

    def test_admin_feature_flag_disabled_blocks_card(self):
        SiteSetting.set_value('agent_digital_card_enabled', False, group='general')
        
        # Public card should 404
        url = reverse('agents:agent_public_card', kwargs={'slug': 'kishan-patel'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

        # vCard should 404
        vcard_url = reverse('agents:agent_card_vcf', kwargs={'slug': 'kishan-patel'})
        vcard_res = self.client.get(vcard_url)
        self.assertEqual(vcard_res.status_code, 404)

        # Lead submission should 403
        lead_url = reverse('agents:agent_card_lead_submit', kwargs={'slug': 'kishan-patel'})
        lead_res = self.client.post(lead_url, {'customer_name': 'Test', 'customer_mobile': '9898989898'})
        self.assertEqual(lead_res.status_code, 403)

    def test_dashboard_hides_all_digital_card_elements_when_flag_off(self):
        SiteSetting.set_value('agent_digital_card_enabled', False, group='general')
        self.client.force_login(self.user)
        response = self.client.get(reverse('agents:agent_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Confirm zero visiting card elements in dashboard navigation or DOM
        self.assertNotContains(response, 'href="#digitalcard"')
        self.assertNotContains(response, 'id="digitalcard-content"')
        self.assertNotContains(response, 'Visiting Card Studio')
        self.assertNotContains(response, 'Customize Card')

    def test_dashboard_shows_digital_card_studio_when_flag_on(self):
        SiteSetting.set_value('agent_digital_card_enabled', True, group='general')
        self.client.force_login(self.user)
        response = self.client.get(reverse('agents:agent_dashboard'))
        self.assertEqual(response.status_code, 200)

        # Confirm navigation tab and studio content are rendered
        self.assertContains(response, 'href="#digitalcard"')
        self.assertContains(response, 'id="digitalcard-content"')
        self.assertContains(response, 'Visiting Card Studio')
        self.assertContains(response, 'Agency &amp; Personal Branding')
        self.assertContains(response, 'Brand Theme Color')

    def test_agent_save_card_customization_api(self):
        SiteSetting.set_value('agent_digital_card_enabled', True, group='general')
        self.client.force_login(self.user)
        url = reverse('agents:agent_save_card_customization')
        data = {
            'agency_name': 'Patel Wealth & Insurance',
            'card_tagline': 'Always Standing By Your Claims',
            'card_bio': '8+ years managing 500+ satisfied family portfolios.',
            'theme_color': '#059669',
            'banner_style': 'gradient_emerald',
            'whatsapp_msg': 'Namaste Kishan, I saw your card and want policy advice.',
            'show_call': '1',
            'show_whatsapp': '1',
            'show_reviews': '0',
            'show_lead_form': '1',
            'custom_button_label': 'Book Video Consultation',
            'custom_button_url': 'https://calendly.com/kishan-patel'
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertTrue(json_data.get('success'))

        # Check model persistence
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.agency_name, 'Patel Wealth & Insurance')
        self.assertEqual(self.profile.card_tagline, 'Always Standing By Your Claims')
        cfg = self.profile.get_card_config()
        self.assertEqual(cfg.get('theme_color'), '#059669')
        self.assertEqual(cfg.get('banner_style'), 'gradient_emerald')
        self.assertEqual(cfg.get('show_reviews'), False)
        self.assertEqual(cfg.get('custom_button_label'), 'Book Video Consultation')

        # Check public card renders customized values
        card_url = reverse('agents:agent_public_card', kwargs={'slug': 'kishan-patel'})
        card_res = self.client.get(card_url)
        self.assertEqual(card_res.status_code, 200)
        self.assertContains(card_res, 'Patel Wealth &amp; Insurance')
        self.assertContains(card_res, 'Always Standing By Your Claims')
        self.assertContains(card_res, '8+ years managing 500+ satisfied family portfolios.')
        self.assertContains(card_res, '#059669')
        self.assertContains(card_res, 'Book Video Consultation')
        self.assertNotContains(card_res, 'id="reviewsHeading"')

    def test_pure_qr_code_endpoint(self):
        url = reverse('agents:agent_card_pure_qr', kwargs={'slug': 'kishan-patel'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(len(response.content) > 100)
