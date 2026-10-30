import json
from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse

from apps.admin_panel.models import RegistrationLead
from apps.agents.models import Agent
from apps.home.models.pincode import Pincode
from apps.agents.services.registration_leads import (
    normalize_phone,
    capture_quick_lead,
    mark_form_started,
    mark_form_completed,
    mark_payment_completed,
    sync_lead_for_agent,
)


class QuickRegistrationLeadsFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.phone = "9876543210"
        self.name = "Vikram Sharma"
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

    def test_normalize_phone_variations(self):
        """Test that normalize_phone always produces the canonical 10-digit phone number."""
        self.assertEqual(normalize_phone("9876543210"), "9876543210")
        self.assertEqual(normalize_phone("+919876543210"), "9876543210")
        self.assertEqual(normalize_phone("919876543210"), "9876543210")
        self.assertEqual(normalize_phone("09876543210"), "9876543210")
        self.assertEqual(normalize_phone("+91 98765 43210"), "9876543210")
        self.assertEqual(normalize_phone(" 98765-43210 "), "9876543210")

    def test_agent_registration_page_shows_eligibility_popup_for_new_visitor(self):
        """Agent registration URL is replaced by the public eligibility popup."""
        response = self.client.get(reverse("agents:agent_registration"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get("registration_popup_only"))
        self.assertFalse(response.context.get("require_quick_reg_gate"))
        self.assertContains(response, 'id="eligibilityPopup"')
        self.assertContains(response, 'data-elig-mode="registration"')
        self.assertNotContains(response, 'id="registrationGate"')

    def test_quick_registration_submission_creates_lead_and_sets_cookie(self):
        """Registration-page gate (name+phone only) still saves a lead and cookie."""
        payload = {
            "name": self.name,
            "phone": "+91 98765 43210",
            "page": "/agent-registration/",
        }
        response = self.client.post(
            reverse("agents:quick_registration"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("redirect"), "")
        self.assertTrue(data.get("reload"))
        self.assertEqual(data.get("lead", {}).get("phone"), self.phone)
        self.assertEqual(data.get("lead", {}).get("name"), self.name)
        self.assertEqual(data.get("lead", {}).get("whatsapp"), self.phone)
        self.assertEqual(data.get("lead", {}).get("status"), RegistrationLead.STATUS_QUICK_REGISTERED)

        # Lead should exist in DB
        lead = RegistrationLead.objects.get(phone=self.phone)
        self.assertEqual(lead.name, self.name)
        self.assertEqual(lead.status, RegistrationLead.STATUS_QUICK_REGISTERED)
        self.assertFalse(lead.form_filled)
        self.assertEqual(lead.payment_status, RegistrationLead.PAYMENT_NONE)

        # Cookie must be set
        self.assertIn("pa_quick_reg_phone", response.cookies)
        self.assertEqual(response.cookies["pa_quick_reg_phone"].value, self.phone)

    def test_duplicate_submission_does_not_create_duplicate_leads(self):
        """Submitting multiple times with same phone updates the existing lead without duplicate rows."""
        gate = {"page": "/agent-registration/"}
        # 1st submission
        self.client.post(
            reverse("agents:quick_registration"),
            data=json.dumps({"name": "Initial Name", "phone": self.phone, **gate}),
            content_type="application/json",
        )
        self.assertEqual(RegistrationLead.objects.filter(phone=self.phone).count(), 1)

        # 2nd submission with updated name
        self.client.post(
            reverse("agents:quick_registration"),
            data=json.dumps({"name": "Updated Name", "phone": self.phone, **gate}),
            content_type="application/json",
        )
        self.assertEqual(RegistrationLead.objects.filter(phone=self.phone).count(), 1)
        lead = RegistrationLead.objects.get(phone=self.phone)
        self.assertEqual(lead.name, "Updated Name")

    def test_quick_registration_blocks_if_mobile_already_active_agent(self):
        """If phone belongs to an existing active agent, quick registration returns 409 Conflict."""
        Agent.objects.create(
            mobile=self.phone,
            fullname="Existing Agent",
            email="existing@example.com",
            status="active",
        )
        response = self.client.post(
            reverse("agents:quick_registration"),
            data=json.dumps({
                "name": "Test User",
                "phone": self.phone,
                "email": "new.user@example.com",
                "pincode": "380001",
                "segments": ["health"],
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data.get("ok"))
        self.assertTrue(data.get("has_account"))
        self.assertIn("/agent-login/", data.get("login_url"))

    def test_page_refresh_still_shows_registration_popup(self):
        """Returning to agent registration always shows the eligibility popup shell."""
        self.client.post(
            reverse("agents:quick_registration"),
            data=json.dumps({"name": self.name, "phone": self.phone, "page": "/agent-registration/"}),
            content_type="application/json",
        )

        response = self.client.get(reverse("agents:agent_registration"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get("registration_popup_only"))
        self.assertContains(response, 'id="eligibilityPopup"')

    def test_progress_endpoint_advances_status_to_form_started(self):
        """Interacting with registration form triggers progress endpoint and advances status to form_started."""
        # Capture lead
        capture_quick_lead(None, self.name, self.phone)
        lead = RegistrationLead.objects.get(phone=self.phone)
        self.assertEqual(lead.status, RegistrationLead.STATUS_QUICK_REGISTERED)

        # Send progress
        response = self.client.post(
            reverse("agents:agent_registration_progress"),
            data=json.dumps({"phone": self.phone}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual(lead.status, RegistrationLead.STATUS_FORM_STARTED)

    def test_step1_completion_advances_status_to_form_completed(self):
        """When step 1 registration is recorded, lead status advances to form_completed and form_filled=True."""
        lead, _ = capture_quick_lead(None, self.name, self.phone)
        mark_form_started(None, lead=lead)
        self.assertEqual(lead.status, RegistrationLead.STATUS_FORM_STARTED)

        mark_form_completed(None, agent=Agent(mobile=self.phone, fullname=self.name))
        lead.refresh_from_db()
        self.assertEqual(lead.status, RegistrationLead.STATUS_FORM_COMPLETED)
        self.assertTrue(lead.form_filled)

    def test_payment_and_conversion_transitions(self):
        """Payment completion marks lead converted with completed payment status and links to Agent."""
        lead, _ = capture_quick_lead(None, self.name, self.phone)
        mark_form_completed(None, agent=Agent(mobile=self.phone, fullname=self.name))

        # Create active agent
        agent = Agent.objects.create(
            mobile=self.phone,
            fullname=self.name,
            email="vikram@example.com",
            status="active",
        )

        mark_payment_completed(agent)
        lead.refresh_from_db()
        self.assertEqual(lead.status, RegistrationLead.STATUS_CONVERTED)
        self.assertEqual(lead.payment_status, RegistrationLead.PAYMENT_COMPLETED)
        self.assertIsNotNone(lead.converted_at)
        self.assertEqual(lead.agent_id, agent.id)


class QuickRegistrationAdminLeadsTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Seed leads with various statuses
        self.lead_quick = RegistrationLead.objects.create(
            name="Aarav Patel",
            phone="9825000001",
            status=RegistrationLead.STATUS_QUICK_REGISTERED,
            form_filled=False,
            payment_status=RegistrationLead.PAYMENT_PENDING,
        )
        self.lead_started = RegistrationLead.objects.create(
            name="Bhavik Shah",
            phone="9825000002",
            status=RegistrationLead.STATUS_FORM_STARTED,
            form_filled=False,
            payment_status=RegistrationLead.PAYMENT_PENDING,
        )
        self.lead_completed = RegistrationLead.objects.create(
            name="Chetan Mehta",
            phone="9825000003",
            status=RegistrationLead.STATUS_FORM_COMPLETED,
            form_filled=True,
            payment_status=RegistrationLead.PAYMENT_PENDING,
        )
        self.lead_converted = RegistrationLead.objects.create(
            name="Deepak Joshi",
            phone="9825000004",
            status=RegistrationLead.STATUS_CONVERTED,
            form_filled=True,
            payment_status=RegistrationLead.PAYMENT_COMPLETED,
            converted_at=timezone.now(),
        )

        # Start patches for admin middleware and views
        self.admin_mock = MagicMock(id=1, role="super", permissions=None)
        self.patch_dashboard_session = patch(
            "apps.admin_panel.views.dashboard._get_admin_from_session", return_value=1
        )
        self.patch_middleware_admin = patch(
            "apps.admin_panel.models.admin_auth.Admin.objects.get", return_value=self.admin_mock
        )
        self.patch_view_leads_session = patch(
            "apps.admin_panel.views.quick_registration_leads._get_admin_from_session", return_value=1
        )
        self.patch_view_agents_session = patch(
            "apps.admin_panel.views.agents._get_admin_from_session", return_value=1
        )

        self.patch_dashboard_session.start()
        self.patch_middleware_admin.start()
        self.patch_view_leads_session.start()
        self.patch_view_agents_session.start()

    def tearDown(self):
        self.patch_view_agents_session.stop()
        self.patch_view_leads_session.stop()
        self.patch_middleware_admin.stop()
        self.patch_dashboard_session.stop()

    def test_default_admin_lead_list_excludes_converted_active_agents(self):
        """Default view (?status=open) shows leads in progress, hiding converted agents."""
        response = self.client.get(reverse("admin_quick_registration_leads"))
        self.assertEqual(response.status_code, 200)
        leads = list(response.context["leads"])
        lead_ids = [l.id for l in leads]

        self.assertIn(self.lead_quick.id, lead_ids)
        self.assertIn(self.lead_started.id, lead_ids)
        self.assertIn(self.lead_completed.id, lead_ids)
        self.assertNotIn(self.lead_converted.id, lead_ids)

    def test_admin_lead_list_status_filter_all_includes_converted(self):
        """When ?status=all is queried, converted leads are visible."""
        response = self.client.get(reverse("admin_quick_registration_leads"), {"status": "all"})
        self.assertEqual(response.status_code, 200)
        leads = list(response.context["leads"])
        lead_ids = [l.id for l in leads]
        self.assertIn(self.lead_converted.id, lead_ids)

    def test_admin_lead_list_form_status_filter(self):
        """Filter by form_status=filled vs unfilled works."""
        # Filled (using query parameter name 'form')
        response_filled = self.client.get(
            reverse("admin_quick_registration_leads"),
            {"status": "all", "form": "filled"},
        )
        filled_ids = [l.id for l in response_filled.context["leads"]]
        self.assertIn(self.lead_completed.id, filled_ids)
        self.assertIn(self.lead_converted.id, filled_ids)
        self.assertNotIn(self.lead_quick.id, filled_ids)

        # Unfilled
        response_unfilled = self.client.get(
            reverse("admin_quick_registration_leads"),
            {"status": "all", "form": "not_filled"},
        )
        unfilled_ids = [l.id for l in response_unfilled.context["leads"]]
        self.assertIn(self.lead_quick.id, unfilled_ids)
        self.assertIn(self.lead_started.id, unfilled_ids)
        self.assertNotIn(self.lead_completed.id, unfilled_ids)

    def test_admin_lead_list_payment_status_filter(self):
        """Filter by payment_status=completed vs pending works."""
        response = self.client.get(
            reverse("admin_quick_registration_leads"),
            {"status": "all", "payment": "completed"},
        )
        completed_ids = [l.id for l in response.context["leads"]]
        self.assertIn(self.lead_converted.id, completed_ids)
        self.assertNotIn(self.lead_quick.id, completed_ids)

    def test_admin_lead_list_search_by_phone_and_name(self):
        """Search query matches either phone or name."""
        response_name = self.client.get(
            reverse("admin_quick_registration_leads"),
            {"status": "all", "search": "Bhavik"},
        )
        leads = list(response_name.context["leads"])
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0].phone, "9825000002")

        response_phone = self.client.get(
            reverse("admin_quick_registration_leads"),
            {"status": "all", "search": "9825000001"},
        )
        leads_phone = list(response_phone.context["leads"])
        self.assertEqual(len(leads_phone), 1)
        self.assertEqual(leads_phone[0].name, "Aarav Patel")

    def test_admin_auto_sync_converts_lead_when_agent_activated(self):
        """If a lead has a matching active agent, loading admin leads automatically syncs and converts it."""
        Agent.objects.create(
            mobile=self.lead_completed.phone,
            fullname=self.lead_completed.name,
            email="chetan@example.com",
            status="active",
        )
        # Fetching the leads page triggers _sync_active_agent_conversions()
        response = self.client.get(reverse("admin_quick_registration_leads"))
        self.assertEqual(response.status_code, 200)

        self.lead_completed.refresh_from_db()
        self.assertEqual(self.lead_completed.status, RegistrationLead.STATUS_CONVERTED)
        self.assertEqual(self.lead_completed.payment_status, RegistrationLead.PAYMENT_COMPLETED)
        # Since it was converted, it must now be excluded from the default open view
        lead_ids = [l.id for l in response.context["leads"]]
        self.assertNotIn(self.lead_completed.id, lead_ids)

    def test_admin_agent_list_search_by_mobile_finds_converted_agent(self):
        """In /admin/agents/?status=active&search=<phone>, agent can be found by phone."""
        Agent.objects.create(
            mobile="9825000009",
            fullname="Elesh Patel",
            email="elesh@example.com",
            status="active",
        )
        response = self.client.get(
            reverse("admin_agents"),
            {"status": "active", "search": "9825000009"},
        )
        self.assertEqual(response.status_code, 200)
        agents = response.context.get("agents")
        self.assertTrue(any(a["mobile"] == "9825000009" for a in agents))

    def test_admin_quick_registration_lead_delete(self):
        """Admin can delete a lead via POST."""
        lead_id = self.lead_quick.id
        response = self.client.post(
            reverse("admin_quick_registration_lead_delete", args=[lead_id]),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RegistrationLead.objects.filter(id=lead_id).exists())
