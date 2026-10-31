from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tests.fakes import FakeGeocoder, ScriptedProvider


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setenv("ADMIN_EMAIL", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "")
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    monkeypatch.setenv("MAX_SEARCHES_PER_MINUTE", "1000")
    monkeypatch.setenv("MAX_SEARCHES_PER_MINUTE_IP", "1000")
    monkeypatch.setenv("MAX_RESULTS_PER_SEARCH", "100")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("EXPORT_DISABLED_FIELDS", "")
    monkeypatch.setenv("EXPORT_FIELD_FLAGS", "")
    monkeypatch.setenv("STORAGE_DISABLED_FIELDS", "")

    from app.config import reset_settings_cache
    from app.database.connection import Base, get_engine, reset_engine
    from app.services.rate_limit import limiter

    reset_settings_cache()
    reset_engine()
    limiter.reset()
    import app.models  # noqa: F401

    Base.metadata.create_all(get_engine())

    box = SimpleNamespace(provider=ScriptedProvider(), geocoder=FakeGeocoder())

    def build(db):
        from app.services.search_service import SearchService

        return SearchService(db, box.provider, box.geocoder)

    monkeypatch.setattr("app.services.container.build_search_service", build)

    from app.main import app

    with TestClient(app) as client:
        box.client = client
        yield box

    limiter.reset()
    reset_engine()
    reset_settings_cache()


@pytest.fixture
def auth(api):
    email = "user@example.com"
    password = "password123"
    registered = api.client.post("/api/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 200, registered.text
    token = registered.json()["access_token"]
    api.headers = {"Authorization": f"Bearer {token}"}
    api.email = email
    api.password = password
    return api
