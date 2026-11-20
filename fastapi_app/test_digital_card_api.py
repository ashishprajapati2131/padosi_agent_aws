"""Tests for Digital Visiting Card FastAPI surface."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.main import app
from fastapi_app.schemas.digital_card import DigitalCardUpdateRequest
from fastapi_app.services.digital_card_service import DigitalCardService


class DigitalCardAuthApiTests(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(
            id=79,
            status="active",
            is_account_active=True,
            email="anil@example.com",
            fullname="Anil Paul Dabhi",
            mobile="9876543210",
            plan_type="professional",
            is_blacklisted=False,
        )
        self.profile = SimpleNamespace(
            agent_id=79,
            slug="anil-paul-dabhi-1",
            display_name="Anil Paul Dabhi",
            agency_name="AP Advisors",
            agency_logo_path=None,
            card_tagline="Trusted Advisor",
            card_config={
                "theme_color": "#0B1F3A",
                "banner_style": "gradient_navy",
                "show_call": True,
                "show_whatsapp": True,
                "show_email": True,
                "show_address": True,
                "show_save_contact": True,
                "show_lead_form": True,
                "show_services": True,
                "show_reviews": True,
                "show_qr_card": True,
                "bio": "Hello",
                "whatsapp_msg": "Hi",
                "custom_button_label": "",
                "custom_button_url": "",
                "custom_banner_path": "",
                "agency_name": "AP Advisors",
                "tagline": "Trusted Advisor",
            },
            is_card_visible=True,
            profile_photo_path=None,
            whatsapp="9876543210",
            office_address="Ahmedabad",
            address="Ahmedabad",
            career_highlights="",
            state="Gujarat",
        )
        self.db = MagicMock()

        def override_agent():
            return self.agent

        def override_db():
            return self.db

        app.dependency_overrides[get_current_agent] = override_agent
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_get_studio_state(self):
        with (
            patch.object(DigitalCardService, "is_feature_enabled", return_value=True),
            patch.object(
                DigitalCardService,
                "get_studio_config",
                return_value={
                    "enabled": True,
                    "allow_theme_customization": True,
                    "allow_custom_banner": True,
                    "allow_custom_logo": True,
                    "allow_custom_button": True,
                    "allow_lead_form_toggle": True,
                    "studio_title": "Studio",
                    "studio_subtitle": "Edit",
                    "default_theme_color": "#0B1F3A",
                    "default_banner_style": "profile",
                    "default_card_tagline": "",
                    "default_card_bio": "",
                    "show_powered_by_badge": True,
                    "powered_by_text": "Powered by PadosiAgent",
                    "policy_call": "allow_agent",
                    "policy_whatsapp": "allow_agent",
                    "policy_email": "allow_agent",
                    "policy_address": "allow_agent",
                    "policy_save_contact": "allow_agent",
                    "policy_lead_form": "allow_agent",
                    "policy_services": "allow_agent",
                    "policy_reviews": "allow_agent",
                    "policy_qr_card": "allow_agent",
                },
            ),
            patch.object(
                DigitalCardService, "get_or_create_profile", return_value=self.profile
            ),
        ):
            resp = self.client.get("/v1/agents/digital-card")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["feature_enabled"])
        self.assertEqual(body["card_config"]["agency_name"], "AP Advisors")
        self.assertIn("card_url", body)
        self.assertTrue(body["card_url"].endswith("/card/anil-paul-dabhi-1/"))

    def test_update_rejects_when_feature_disabled(self):
        with patch.object(DigitalCardService, "is_feature_enabled", return_value=False):
            resp = self.client.patch(
                "/v1/agents/digital-card",
                json={"agency_name": "New Name"},
            )
        self.assertEqual(resp.status_code, 403)

    def test_update_card_settings(self):
        with (
            patch.object(DigitalCardService, "is_feature_enabled", return_value=True),
            patch.object(
                DigitalCardService,
                "get_studio_config",
                return_value={
                    "enabled": True,
                    "allow_theme_customization": True,
                    "allow_custom_banner": True,
                    "allow_custom_logo": True,
                    "allow_custom_button": True,
                    "allow_lead_form_toggle": True,
                },
            ),
            patch.object(
                DigitalCardService, "get_or_create_profile", return_value=self.profile
            ),
        ):
            resp = self.client.patch(
                "/v1/agents/digital-card",
                json={
                    "agency_name": "New Agency",
                    "card_tagline": "New Tag",
                    "theme_color": "#123456",
                    "show_lead_form": False,
                },
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["card_config"]["agency_name"], "New Agency")
        self.assertEqual(body["card_config"]["theme_color"], "#123456")
        self.assertFalse(body["card_config"]["show_lead_form"])
        self.db.commit.assert_called()


class DigitalCardServiceUnitTests(unittest.TestCase):
    def test_always_hide_policy_overrides_agent(self):
        from apps.admin_panel.services.digital_card_studio import (
            resolve_effective_section_visibility as resolve,
        )

        studio = {
            "policy_call": "always_hide",
            "policy_email": "allow_agent",
            "policy_whatsapp": "always_show",
        }
        self.assertFalse(resolve("policy_call", True, studio))
        self.assertTrue(resolve("policy_whatsapp", False, studio))
        self.assertTrue(resolve("policy_email", True, studio))

        db = MagicMock()
        svc = DigitalCardService(db)
        cfg = {"show_call": True, "show_whatsapp": False, "show_email": True}
        full_studio = {
            **studio,
            "policy_address": "allow_agent",
            "policy_save_contact": "allow_agent",
            "policy_lead_form": "allow_agent",
            "policy_services": "allow_agent",
            "policy_reviews": "allow_agent",
            "policy_qr_card": "allow_agent",
        }
        sections = svc.resolve_effective_sections(cfg, full_studio)
        self.assertFalse(sections["call"])
        self.assertTrue(sections["whatsapp"])
        self.assertTrue(sections["email"])

    def test_sanitize_blocks_javascript_url(self):
        svc = DigitalCardService(MagicMock())
        self.assertEqual(svc._sanitize_custom_url("javascript:alert(1)"), "")
        self.assertTrue(svc._sanitize_custom_url("example.com").startswith("https://"))

    def test_update_request_rejects_bad_theme(self):
        with self.assertRaises(Exception):
            DigitalCardUpdateRequest(theme_color="red")

    def test_public_hidden_when_not_visible(self):
        db = MagicMock()
        svc = DigitalCardService(db)
        agent = SimpleNamespace(
            id=1, status="active", is_blacklisted=False, fullname="A", email="a@x.com", mobile="9"
        )
        profile = SimpleNamespace(
            slug="a",
            is_card_visible=False,
            display_name="A",
            agency_name="",
            agency_logo_path=None,
            card_tagline="",
            card_config={},
            profile_photo_path=None,
            whatsapp="",
            office_address="",
            address="",
            career_highlights="",
            state="gj",
        )
        with (
            patch.object(svc, "is_feature_enabled", return_value=True),
            patch.object(svc, "_agent_hidden", return_value=False),
        ):
            with self.assertRaises(HTTPException) as ctx:
                svc.build_public_payload(agent, profile)
        self.assertEqual(ctx.exception.status_code, 404)


class PublicDigitalCardApiTests(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_public_card_404_when_missing(self):
        with patch.object(
            DigitalCardService, "get_profile_by_slug", return_value=(None, None)
        ):
            resp = self.client.get("/v1/public/digital-card/missing-slug")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
