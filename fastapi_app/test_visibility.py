import unittest
from types import SimpleNamespace

from starlette.testclient import TestClient

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.main import app
from fastapi_app.services.visibility_service import VISIBILITY_FIELDS


class _Query:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.result


class _DB:
    def __init__(self, profile):
        self.profile = profile
        self.committed = False

    def query(self, model):
        return _Query(self.profile)

    def commit(self):
        self.committed = True

    def close(self):
        pass


def _profile(**overrides):
    data = {name: True for name in VISIBILITY_FIELDS}
    data.update(overrides)
    return SimpleNamespace(**data)


class VisibilityApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)
        self.profile = _profile(show_reviews=True)
        self.db = _DB(self.profile)
        app.dependency_overrides[get_current_agent] = lambda: SimpleNamespace(id=7)

        def _db():
            yield self.db

        app.dependency_overrides[get_db] = _db

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_routes_are_registered(self):
        paths = app.openapi()["paths"]
        self.assertIn("/v1/agents/profile/visibility", paths)
        self.assertIn("post", paths["/v1/agents/profile/visibility"])
        self.assertIn("get", paths["/v1/agents/profile/visibility"])
        self.assertIn("/v1/agents/update-visibility", paths)

    def test_update_turns_a_section_off(self):
        response = self.client.post(
            "/v1/agents/update-visibility",
            json={"field": "show_reviews", "value": False},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["field"], "show_reviews")
        self.assertFalse(body["value"])
        self.assertFalse(body["visibility"]["show_reviews"])
        self.assertTrue(body["visibility"]["show_certificates"])
        self.assertFalse(self.profile.show_reviews)
        self.assertTrue(self.db.committed)

    def test_profile_visibility_path_accepts_website_style_value(self):
        response = self.client.post(
            "/v1/agents/profile/visibility/",
            json={"field": "show_certificates", "value": 0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["visibility"]["show_certificates"])

    def test_invalid_field_is_rejected(self):
        response = self.client.post(
            "/v1/agents/profile/visibility",
            json={"field": "is_profile_visible", "value": False},
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.db.committed)
        self.assertTrue(self.profile.show_reviews)

    def test_missing_profile_returns_404(self):
        self.db.profile = None
        response = self.client.get("/v1/agents/profile/visibility")
        self.assertEqual(response.status_code, 404)

    def test_missing_token_is_rejected(self):
        app.dependency_overrides.clear()
        response = self.client.post(
            "/v1/agents/update-visibility",
            json={"field": "show_reviews", "value": False},
        )
        self.assertIn(response.status_code, (401, 403))
