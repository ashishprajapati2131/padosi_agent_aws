from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from apps.agents.models import Agent, AgentProfile, AgentLead
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
