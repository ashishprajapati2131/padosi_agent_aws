"""Public eligibility popup → draft → welcome card/website preview → choose plan."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.admin_panel.models import RegistrationLead
from apps.agents.models import Agent, AgentDraft, AgentInsuranceSegment, AgentProfile
from apps.agents.services.og_image import _agent_segment_pills, _share_experience_years
from apps.agents.services.og_meta import profile_og_context
from apps.home.models.pincode import Pincode


def _popup_payload(**overrides):
    data = {
        'name': 'Maheshkumar Parmar',
        'phone': '9876543210',
        'email': 'mahesh.parmar@example.com',
        'pincode': '380001',
        'segments': ['health', 'life'],
        'page': '/',
    }
    data.update(overrides)
    return data


class PopupWelcomePreviewTests(TestCase):
    def setUp(self):
        Pincode.objects.get_or_create(
            pincode='380001',
            defaults={
                'office_name': 'Ahmedabad GPO',
                'district': 'Ahmedabad',
                'state': 'Gujarat',
                'latitude': '23.02250000',
                'longitude': '72.57140000',
            },
        )

    def _pin_row(self):
        return SimpleNamespace(state='Gujarat', pincode='380001')

    @patch('apps.agents.views.registration._resolve_registration_pincode')
    def test_public_popup_creates_draft_and_redirects_to_welcome_preview(self, resolve_pin):
        resolve_pin.return_value = self._pin_row()
        response = self.client.post(
            reverse('agents:quick_registration'),
            data=json.dumps(_popup_payload()),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('/welcome-preview/', data.get('redirect', ''))
        self.assertNotIn('agent-registration', data.get('redirect', ''))
        self.assertNotIn('chooseplan', data.get('redirect', ''))

        draft = AgentDraft.objects.get(email__iexact='mahesh.parmar@example.com')
        self.assertEqual(draft.fullname, 'Maheshkumar Parmar')
        self.assertEqual(draft.mobile, '9876543210')
        self.assertEqual(draft.agent_pincode, '380001')
        self.assertEqual(draft.state, 'Gujarat')
        self.assertEqual(sorted(draft.segments), ['health', 'life'])
        self.assertEqual(self.client.session.get('current_draft_id'), draft.pk)
        self.assertEqual(self.client.session.get('post_payment_landing'), 'edit_profile')
        self.assertTrue(RegistrationLead.objects.filter(phone='9876543210').exists())

    @patch('apps.agents.views.registration._resolve_registration_pincode')
    def test_full_popup_from_registration_page_path_creates_draft(self, resolve_pin):
        resolve_pin.return_value = self._pin_row()
        payload = _popup_payload(page='/agent-registration/')
        response = self.client.post(
            reverse('agents:quick_registration'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data.get('ok'))
        self.assertIn('/welcome-preview/', data.get('redirect', ''))
        self.assertTrue(AgentDraft.objects.filter(email__iexact='mahesh.parmar@example.com').exists())

    @patch('apps.agents.views.registration._resolve_registration_pincode')
    def test_public_popup_requires_email_pincode_and_segment(self, resolve_pin):
        resolve_pin.return_value = self._pin_row()
        response = self.client.post(
            reverse('agents:quick_registration'),
            data=json.dumps({'name': 'Maheshkumar Parmar', 'phone': '9876543210', 'page': '/'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 422)
        errors = response.json().get('errors') or {}
        self.assertIn('email', errors)
        self.assertIn('pincode', errors)
        self.assertIn('segments', errors)
        self.assertFalse(AgentDraft.objects.exists())

    @patch('apps.agents.views.registration._resolve_registration_pincode')
    def test_welcome_preview_shows_card_and_website(self, resolve_pin):
        resolve_pin.return_value = self._pin_row()
        self.client.post(
            reverse('agents:quick_registration'),
            data=json.dumps(_popup_payload()),
            content_type='application/json',
        )
        page = self.client.get(reverse('agents:welcome_preview'))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context.get('welcome_preview_mode'))
        self.assertContains(page, 'reg-preview-overlay')
        self.assertContains(page, 'Claim offer')
        self.assertContains(page, 'Your personal website URL')
        self.assertNotContains(page, 'id="registrationGate"')
        self.assertIn('/chooseplan/', page.content.decode())
        self.assertNotIn("postSubmitRedirect: '/agent-registration/", page.content.decode())

    def test_welcome_preview_without_draft_does_not_open_registration(self):
        response = self.client.get(reverse('agents:welcome_preview'))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('agent-registration', response['Location'])

    def test_home_shows_eligibility_popup_profile_does_not(self):
        agent = Agent.objects.create(
            fullname='Maheshkumar Parmar',
            email='mahesh.profile@example.com',
            mobile='9876500001',
            status='active',
        )
        AgentProfile.objects.create(
            agent=agent,
            slug='parmar-maheshkumar',
            display_name='Maheshkumar Parmar',
            is_profile_visible=True,
        )
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, 'id="eligibilityPopup"')

        profile = self.client.get('/gj/parmar-maheshkumar/')
        self.assertEqual(profile.status_code, 200)
        self.assertNotContains(profile, 'id="eligibilityPopup"')

    def test_og_pills_use_agent_segments_and_skip_placeholders(self):
        agent = Agent.objects.create(
            fullname='Segment Agent',
            email='seg.agent@example.com',
            mobile='9876500002',
            status='active',
            experience_range='7',
        )
        AgentProfile.objects.create(
            agent=agent,
            slug='segment-agent',
            display_name='Segment Agent',
            experience_years=7,
            is_profile_visible=True,
        )
        AgentInsuranceSegment.objects.create(agent=agent, segment_type='life')
        AgentInsuranceSegment.objects.create(agent=agent, segment_type='sme')
        pills = _agent_segment_pills(agent)
        names = [p['name'] for p in pills]
        self.assertIn('Life', names)
        self.assertIn('SME Insurance', names)
        self.assertNotIn('Health', names)
        self.assertNotIn('Motor', names)

        request = RequestFactory().get('/gj/segment-agent/')
        ctx = profile_og_context(request, agent, display_name='Segment Agent')
        self.assertEqual(
            ctx['og_share_description'],
            'Segment Agent | Licensed Insurance & Financial Advisor',
        )
        self.assertEqual(ctx['og_share_title'], ctx['og_share_description'])
        self.assertNotIn('yrs exp', ctx['og_share_description'])

    def test_share_card_uses_agent_experience_when_profile_years_are_blank(self):
        agent = Agent.objects.create(
            fullname='Range Agent',
            email='range.agent@example.com',
            mobile='9876500003',
            status='active',
            experience_range='12',
        )
        profile = AgentProfile.objects.create(
            agent=agent,
            slug='range-agent',
            display_name='Range Agent',
            experience_years=0,
            is_profile_visible=True,
        )
        self.assertEqual(_share_experience_years(agent, profile), 12)
        request = RequestFactory().get('/gj/range-agent/')
        ctx = profile_og_context(request, agent, display_name='Range Agent')
        self.assertEqual(
            ctx['og_share_description'],
            'Range Agent | Licensed Insurance & Financial Advisor',
        )

        other = Agent.objects.create(
            fullname='Four Year Agent',
            email='four.year@example.com',
            mobile='9876500004',
            status='active',
            experience_range='4',
        )
        other_profile = AgentProfile.objects.create(
            agent=other,
            slug='four-year-agent',
            display_name='Four Year Agent',
            experience_years=15,
            is_profile_visible=True,
        )
        self.assertEqual(_share_experience_years(other, other_profile), 4)
