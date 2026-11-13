"""
Audit fixes for the profile / leads API:
API5  upload endpoints read with a size cap and run blocking work in the threadpool
API8  GET /leads returns no lead rows while lead_management is locked
API9  website / social links validated like Django and saved under Django's keys
API10 agent-added cities: validated, reused, pending review, capped per day
API18 lead preference bounds and typed career timeline body
"""

import asyncio
import datetime
import io
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.cache.backends.locmem import LocMemCache
from django.test import TestCase
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from fastapi_app.repositories.agent_lead_repository import AgentLeadRepository
from fastapi_app.routers import profile as profile_router
from fastapi_app.routers.leads import list_leads
from fastapi_app.schemas.leads import LeadPreferencesRequest
from fastapi_app.schemas.profile import (
    CareerTimelineWriteRequest,
    LeadPreferenceInputSchema,
    LeadPreferenceSchema,
    SocialLinksSchema,
)
from fastapi_app.services.profile_service import ProfileService


class LeadsLockedListTests(unittest.TestCase):
    def _call(self, locked):
        repo = MagicMock()
        repo.get_leads_paginated.return_value = ([], 0)
        with patch("fastapi_app.routers.leads.LockUnlockService") as lock_cls:
            lock_cls.return_value.get_feature_access_map.return_value = {
                "lead_management": {"is_locked": locked, "unlock_hint": "Upgrade"}
            }
            resp = list_leads(
                page=1,
                page_size=20,
                status_filter=None,
                interaction_type=None,
                search=None,
                current_agent=MagicMock(id=7),
                db=MagicMock(),
                repo=repo,
            )
        return resp, repo

    def test_locked_returns_empty_list_same_shape(self):
        resp, repo = self._call(True)
        repo.get_leads_paginated.assert_not_called()
        self.assertEqual(
            (resp.leads, resp.total, resp.is_locked, resp.page), ([], 0, True, 1)
        )
        self.assertEqual(resp.unlock_hint, "Upgrade")

    def test_unlocked_unchanged(self):
        resp, repo = self._call(False)
        repo.get_leads_paginated.assert_called_once()
        self.assertFalse(resp.is_locked)


class LeadPreferenceBoundsTests(unittest.TestCase):
    def test_bounds(self):
        for model in (LeadPreferencesRequest, LeadPreferenceInputSchema):
            for bad in (
                {"portfolio_fee": -1},
                {"claims_fee_amount": 10_000_001},
                {"claims_percent": 101},
                {"claims_percent": -0.5},
                {"portfolio_charging": "x" * 51},
            ):
                with self.assertRaises(ValidationError, msg=(model, bad)):
                    model(**bad)
            ok = model(
                portfolio_fee=500, claims_percent=None, claims_charging="percentage"
            )
            self.assertIsNone(ok.claims_percent)

    def test_response_schema_still_loads_old_rows(self):
        self.assertEqual(LeadPreferenceSchema(portfolio_fee=-5).portfolio_fee, -5)

    def test_repository_handles_null_numbers(self):
        db = MagicMock()
        repo = AgentLeadRepository(db)
        pref = SimpleNamespace()
        with patch.object(repo, "get_preferences", return_value=pref):
            repo.save_preferences(
                1,
                LeadPreferencesRequest(
                    claims_percent=None, portfolio_fee=None
                ).model_dump(),
            )
        self.assertEqual((pref.claims_percent, pref.portfolio_fee), (0.0, 0.0))


class CareerTimelineSchemaTests(unittest.TestCase):
    def test_year_range_and_coercion(self):
        nxt = datetime.date.today().year + 1
        self.assertEqual(CareerTimelineWriteRequest(year=2015).year, "2015")
        self.assertEqual(CareerTimelineWriteRequest(year=str(nxt)).year, str(nxt))
        for bad in (1949, nxt + 1, "abcd", "20155"):
            with self.assertRaises(ValidationError):
                CareerTimelineWriteRequest(year=bad)
        self.assertEqual(CareerTimelineWriteRequest(month=3).month, "3")

    def test_lengths_and_partial_dump(self):
        with self.assertRaises(ValidationError):
            CareerTimelineWriteRequest(title="x" * 2001)
        with self.assertRaises(ValidationError):
            CareerTimelineWriteRequest(suggestion_key="k" * 51)
        body = CareerTimelineWriteRequest(title="Joined LIC").model_dump(
            exclude_none=True
        )
        self.assertEqual(body, {"title": "Joined LIC"})


class DigitalPresenceTests(unittest.TestCase):
    def _clean(self, website="", profile=None, **links):
        return ProfileService._clean_digital_presence(
            website, SocialLinksSchema(**links), profile
        )

    def test_saves_django_keys_normalized(self):
        website, socials = self._clean(
            "example.com", linkedin_url="www.linkedin.com/in/x"
        )
        self.assertEqual(website, "https://example.com")
        self.assertEqual(socials["linkedin"], "https://www.linkedin.com/in/x")
        self.assertEqual(
            set(socials),
            {"google_business", "linkedin", "instagram", "facebook", "youtube"},
        )

    def test_rejects_script_and_wrong_host(self):
        for kwargs in (
            {"website": "javascript:alert(1)"},
            {"instagram_url": "https://evil.com/x"},
            {"youtube_url": "data:text/html,hi"},
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._clean(**kwargs)
            self.assertEqual(ctx.exception.status_code, 422)

    def test_unchanged_legacy_value_kept(self):
        profile = SimpleNamespace(
            website_url="my site", social_links={"linkedin_url": "John Smith"}
        )
        website, socials = self._clean("my site", profile, linkedin_url="John Smith")
        self.assertEqual((website, socials["linkedin"]), ("my site", "John Smith"))

    def test_saved_socials_reads_old_and_new_keys(self):
        self.assertEqual(
            ProfileService._saved_socials('{"instagram_url": "a", "linkedin": "b"}')[
                "instagram"
            ],
            "a",
        )
        self.assertEqual(
            ProfileService._saved_socials({"linkedin": "b"})["linkedin"], "b"
        )


class CappedUploadTests(unittest.TestCase):
    def test_read_is_capped(self):
        f = UploadFile(file=io.BytesIO(b"a" * 5000), filename="x.jpg")
        self.assertEqual(
            len(asyncio.run(profile_router._read_upload_capped(f, 1000))), 1001
        )
        f = UploadFile(file=io.BytesIO(b"a" * 10), filename="x.jpg")
        self.assertEqual(
            len(asyncio.run(profile_router._read_upload_capped(f, 1000))), 10
        )

    def test_oversize_profile_image_rejected_before_db(self):
        db = MagicMock()
        big = UploadFile(
            file=io.BytesIO(b"a" * (profile_router._IMAGE_MAX_BYTES + 10)),
            filename="p.jpg",
        )
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                profile_router.upload_profile_image(
                    request=None, file=big, current_agent=MagicMock(id=1), db=db
                )
            )
        self.assertEqual(ctx.exception.status_code, 422)
        db.query.assert_not_called()


class AddCityTests(TestCase):
    def setUp(self):
        self.cache = LocMemCache("apiprof-city", {})
        p = patch("fastapi_app.routers.profile.shared_cache", return_value=self.cache)
        p.start()
        self.addCleanup(p.stop)
        self.agent = MagicMock(id=987654)

    def _add(self, name):
        return profile_router.add_serviceable_city(
            payload=profile_router.CityCreateRequest(name=name),
            current_agent=self.agent,
            db=MagicMock(),
        )

    def test_validation_reuse_pending_and_cap(self):
        from apps.agents.models import City

        for bad in ("A", "x" * 61, "<script>", "123", "Pune1", "..."):
            with self.assertRaises(HTTPException, msg=bad):
                self._add(bad)
        created = self._add("  Navi   Mumbaiz ")
        self.assertEqual(created["city"]["name"], "Navi Mumbaiz")
        self.assertTrue(City.objects.get(id=created["city"]["id"]).is_active)  # live at once, as before
        again = self._add("navi mumbaiz")
        self.assertEqual(again["city"]["id"], created["city"]["id"])
        self.assertEqual(again["message"], "City already exists.")
        for i in range(4):
            self._add(f"Testtown {'abcd'[i]}")
        with self.assertRaises(HTTPException) as ctx:
            self._add("Testtown e")
        self.assertEqual(ctx.exception.status_code, 429)
