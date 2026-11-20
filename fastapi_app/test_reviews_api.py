"""Tests for GET /v1/agents/reviews (agent management list)."""

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.main import app
from fastapi_app.repositories.agent_review_repository import AgentReviewRepository


class ReviewsListApiTests(unittest.TestCase):
    def setUp(self):
        self.agent = SimpleNamespace(
            id=42,
            status="active",
            is_account_active=True,
            email="agent@example.com",
            plan_type="professional",
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

    def _review(self, rid=1, approved=True, rating=5, name="Patel"):
        return SimpleNamespace(
            id=rid,
            reviewer_name=name,
            rating=rating,
            review="Great service",
            is_approved=approved,
            created_at=datetime(2026, 1, 15, 10, 0, 0),
        )

    def test_list_reviews_unlocked(self):
        reviews = [self._review(1), self._review(2, approved=False, rating=4, name="Shah")]
        with (
            patch(
                "fastapi_app.routers.reviews.LockUnlockService"
            ) as lock_cls,
            patch.object(
                AgentReviewRepository,
                "get_reviews_paginated",
                return_value=(reviews, 2),
            ),
            patch.object(AgentReviewRepository, "count_approved", return_value=1),
            patch.object(AgentReviewRepository, "count_pending", return_value=1),
            patch.object(
                AgentReviewRepository, "average_approved_rating", return_value=5.0
            ),
        ):
            lock_cls.return_value.get_feature_access_map.return_value = {
                "view_reviews": {"is_locked": False, "unlock_hint": None}
            }
            resp = self.client.get("/v1/agents/reviews?page=1&page_size=20")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["reviews"]), 2)
        self.assertFalse(body["is_locked"])
        self.assertEqual(body["approved_count"], 1)
        self.assertEqual(body["pending_count"], 1)
        self.assertNotIn("reviewer_email", body["reviews"][0])
        self.assertNotIn("reviewer_mobile", body["reviews"][0])

    def test_list_reviews_locked_returns_empty(self):
        with (
            patch(
                "fastapi_app.routers.reviews.LockUnlockService"
            ) as lock_cls,
            patch.object(AgentReviewRepository, "count_approved", return_value=3),
            patch.object(AgentReviewRepository, "count_pending", return_value=0),
            patch.object(
                AgentReviewRepository, "average_approved_rating", return_value=4.5
            ),
            patch.object(
                AgentReviewRepository, "get_reviews_paginated"
            ) as paginated,
        ):
            lock_cls.return_value.get_feature_access_map.return_value = {
                "view_reviews": {
                    "is_locked": True,
                    "unlock_hint": "Get 2 more reviews to unlock",
                }
            }
            resp = self.client.get("/v1/agents/reviews")
            paginated.assert_not_called()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["is_locked"])
        self.assertEqual(body["reviews"], [])
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["average_rating"], 4.5)
        self.assertIn("reviews", body["unlock_hint"].lower() or "reviews")


class ReviewUnlockCountTests(unittest.TestCase):
    def test_lock_metrics_filter_includes_verified_user(self):
        import inspect
        from fastapi_app.services import lock_unlock_service as lus

        source = inspect.getsource(lus.LockUnlockService.collect_agent_metrics)
        self.assertIn("user_id.isnot(None)", source)
        self.assertIn("is_approved == True", source)


if __name__ == "__main__":
    unittest.main()
