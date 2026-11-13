"""API audit items API6, API7, API14, API15, API16, API17 (mobile API, no DB: mocked sessions)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.testclient import TestClient

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.main import app
from fastapi_app.models.agent_subscription import AgentSubscription
from fastapi_app.services.lock_unlock_service import (
    LockUnlockService,
    agent_subscription_expired,
)


def _paid_db(has_paid, has_valid):
    db = MagicMock()
    paid = db.query.return_value.filter.return_value
    paid.first.return_value = object() if has_paid else None
    paid.filter.return_value.first.return_value = object() if has_valid else None
    return db


class SubscriptionExpiryTests(unittest.TestCase):
    """API6: invariant 12 in the API, only while the admin switch is ON."""

    def test_switch_off_never_expires_and_skips_queries(self):
        db = MagicMock()
        with patch(
            "apps.agents.services.subscription_expiry.expiry_enforced",
            return_value=False,
        ):
            self.assertFalse(agent_subscription_expired(db, SimpleNamespace(id=1)))
        db.query.assert_not_called()

    def test_switch_on_rule_matches_django(self):
        agent = SimpleNamespace(id=1)
        with (
            patch(
                "apps.agents.services.subscription_expiry.expiry_enforced",
                return_value=True,
            ),
            patch(
                "apps.event_referral.services.participant_service.event_referral_grants_dashboard",
                return_value=False,
            ),
        ):
            self.assertTrue(agent_subscription_expired(_paid_db(True, False), agent))
            self.assertFalse(
                agent_subscription_expired(_paid_db(True, True), agent)
            )  # still valid / NULL expiry
            self.assertFalse(
                agent_subscription_expired(_paid_db(False, False), agent)
            )  # never paid: not "expired"

    def test_event_referral_challenger_keeps_access(self):
        with (
            patch(
                "apps.agents.services.subscription_expiry.expiry_enforced",
                return_value=True,
            ),
            patch(
                "apps.event_referral.services.participant_service.event_referral_grants_dashboard",
                return_value=True,
            ),
        ):
            self.assertFalse(
                agent_subscription_expired(_paid_db(True, False), SimpleNamespace(id=1))
            )

    def _call(self, route_path, expired):
        agent = SimpleNamespace(
            id=7, status="active", is_account_active=True, email="a@x.com"
        )
        request = (
            None
            if route_path is None
            else SimpleNamespace(scope={"route": SimpleNamespace(path=route_path)})
        )
        user = SimpleNamespace(email="a@x.com", id=3)
        with (
            patch("fastapi_app.dependencies.auth.AgentRepository") as repo,
            patch(
                "fastapi_app.services.lock_unlock_service.agent_subscription_expired",
                return_value=expired,
            ),
        ):
            repo.return_value.get_by_email.return_value = agent
            return get_current_agent(request=request, current_user=user, db=MagicMock())

    def test_expired_agent_gets_403_on_paid_routes(self):
        with self.assertRaises(HTTPException) as ctx:
            self._call("/v1/agents/dashboard", expired=True)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("subscription has expired", ctx.exception.detail)

    def test_renewal_and_logout_stay_open(self):
        for path in (
            "/v1/agents/me",
            "/v1/agents/logout",
            "/v1/agents/plans",
            "/v1/agents/plan-upgrade/handoff",
            None,
        ):
            self.assertEqual(self._call(path, expired=True).id, 7)

    def test_valid_agent_unchanged(self):
        self.assertEqual(self._call("/v1/agents/dashboard", expired=False).id, 7)


class FeatureMapMemoTests(unittest.TestCase):
    """API16: one feature-map computation per agent per request."""

    def test_gates_reuse_map_for_same_agent_only(self):
        svc = LockUnlockService(MagicMock())
        metrics = {"reviews": 0}
        with (
            patch.object(
                LockUnlockService,
                "get_site_setting_json",
                side_effect=lambda k, d=None: d,
            ),
            patch.object(
                LockUnlockService, "collect_agent_metrics", return_value=metrics
            ) as collect,
        ):
            agent = SimpleNamespace(id=1, plan_type="professional")
            svc.is_feature_unlocked(agent, "edit_profile")
            LockUnlockService(MagicMock()).require_feature_unlocked(
                agent, "edit_profile_basic"
            )
            self.assertEqual(collect.call_count, 1)
            # A new request loads a new agent object: computed again.
            svc.is_feature_unlocked(
                SimpleNamespace(id=1, plan_type="professional"), "edit_profile"
            )
            self.assertEqual(collect.call_count, 2)
            # The public map is always fresh (callers return it after writes).
            svc.get_feature_access_map(agent)
            self.assertEqual(collect.call_count, 3)


class _Stop(Exception):
    pass


class DashboardSubscriptionTests(unittest.TestCase):
    """API7: NULL expires_at counts as active (Django still_valid_q)."""

    def test_active_subscription_filter_keeps_null_expiry(self):
        from fastapi_app.services.dashboard_service import DashboardService

        captured = {}
        db = MagicMock()

        def query(model, *a):
            q = MagicMock()
            if model is AgentSubscription:

                def flt(*clauses):
                    captured["sql"] = " ".join(str(c) for c in clauses)
                    raise _Stop

                q.filter.side_effect = flt
            return q

        db.query.side_effect = query
        with self.assertRaises(_Stop):
            DashboardService(db).get_dashboard(SimpleNamespace(id=5))
        self.assertIn(
            "agent_subscriptions.expires_at IS NULL OR agent_subscriptions.expires_at >",
            captured["sql"],
        )


class ChampionshipPublicTests(unittest.TestCase):
    """API14 / API15: public championship endpoints."""

    def setUp(self):
        self.db = MagicMock()
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app, raise_server_exceptions=False)
        self.campaign = SimpleNamespace(
            id=1, social_channels=[{"platform": "instagram"}, {"platform": "facebook"}]
        )
        p = patch(
            "fastapi_app.routers.championship.get_current_campaign",
            return_value=self.campaign,
        )
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        app.dependency_overrides.pop(get_db, None)

    def test_unknown_ref_id_is_404(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        res = self.client.get("/v1/championship/public/landing/PA-NOPE")
        self.assertEqual(res.status_code, 404)

    def test_follow_validates_lengths_and_platform(self):
        url = "/v1/championship/public/social-follow"
        self.assertEqual(
            self.client.post(
                url, json={"session_id": "s" * 65, "platform": "instagram"}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                url, json={"session_id": "s1", "platform": "x" * 33}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.post(
                url, json={"session_id": "s1", "platform": "tiktok"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/v1/championship/public/scratch-reveal", json={"session_id": "s" * 65}
            ).status_code,
            422,
        )
        self.db.add.assert_not_called()

    def test_repeat_follow_adds_no_row(self):
        q = self.db.query.return_value.filter.return_value
        q.all.return_value = [("instagram",)]
        q.first.return_value = SimpleNamespace(
            id=1, is_revealed=False
        )  # already followed
        res = self.client.post(
            "/v1/championship/public/social-follow",
            json={"session_id": "s1", "platform": "Instagram"},
        )
        self.assertEqual(res.status_code, 200)
        self.db.add.assert_not_called()
        q.first.return_value = None  # first follow
        self.client.post(
            "/v1/championship/public/social-follow",
            json={"session_id": "s2", "platform": "facebook"},
        )
        self.db.add.assert_called_once()


class ReferralCodeTests(unittest.TestCase):
    """API17: collisions and parallel creation."""

    def _db(self, first_results, commit_errors):
        db = MagicMock()
        chain = db.query.return_value.filter.return_value
        chain.first.side_effect = first_results
        chain.count.return_value = 0
        db.commit.side_effect = commit_errors
        return db

    def test_parallel_creation_reuses_existing_code(self):
        from fastapi_app.routers.referral import get_referral_details

        existing = MagicMock(code="ABCD1234", total_referrals=0)
        db = self._db(
            [None, existing], [IntegrityError("x", {}, Exception("dup")), None]
        )
        res = get_referral_details(current_agent=SimpleNamespace(id=9), db=db)
        db.rollback.assert_called_once()
        self.assertEqual(res["referral_code"], "ABCD1234")

    def test_code_collision_retries(self):
        from fastapi_app.routers.referral import get_referral_details

        db = self._db(
            [None, None], [IntegrityError("x", {}, Exception("dup")), None, None]
        )
        res = get_referral_details(current_agent=SimpleNamespace(id=9), db=db)
        self.assertEqual(db.add.call_count, 2)
        self.assertEqual(len(res["referral_code"]), 8)


if __name__ == "__main__":
    unittest.main()
