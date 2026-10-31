from app.services.errors import QUOTA_MESSAGE, GoogleServiceError, LocationNotFoundError
from app.services.normalized import NormalizedPlace
from tests.fakes import InfiniteProvider


def _search(api, **overrides):
    body = {
        "category": "Hotel",
        "location": "Ahmedabad",
        "radius_km": 5,
        "max_results": 20,
    }
    body.update(overrides)
    return api.client.post("/api/search", json=body, headers=api.headers)


def test_search_request_validation(auth):
    missing = auth.client.post("/api/search", json={"location": "Ahmedabad"}, headers=auth.headers)
    assert missing.status_code == 422
    coords = _search(auth, location="23.02, 72.57")
    assert coords.status_code == 422
    assert "Coordinates" in coords.json()["detail"]
    assert auth.geocoder.calls == []


def test_generic_text_search_flow(auth):
    response = _search(auth, category="Petrol Pump", location="Ahmedabad 380015", keyword="24 hour")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["search"]["query"] == "Petrol Pump 24 hour Ahmedabad 380015"
    assert auth.geocoder.calls == ["Ahmedabad 380015"]
    assert auth.provider.calls[0].mode == "text"
    assert auth.provider.calls[0].text_query == "Petrol Pump 24 hour Ahmedabad 380015"
    assert auth.provider.calls[0].radius_meters == 5000
    assert body["search"]["formatted_address"] == "Ahmedabad, Gujarat, India"
    assert body["search"]["result_count"] == 1
    assert body["total"] == 1
    assert "Showing" not in (body.get("message") or "")
    assert body["results"][0]["name"] == "River Hotel"


def test_nearby_passes_category_through_without_a_lookup_table(auth):
    response = _search(auth, category="Petrol Pump", location="Ahmedabad", search_mode="nearby", radius_km=1.5)
    assert response.status_code == 200, response.text
    request = auth.provider.calls[0]
    assert request.mode == "nearby"
    assert request.included_types == ["petrol_pump"]
    assert request.radius_meters == 1500


def test_pagination_stops_at_cap(auth, monkeypatch):
    monkeypatch.setenv("MAX_RESULTS_PER_SEARCH", "25")
    from app.config import reset_settings_cache

    reset_settings_cache()
    auth.provider = InfiniteProvider()
    response = _search(auth, max_results=500)
    assert response.status_code == 200, response.text
    assert response.json()["search"]["result_count"] == 25
    assert response.json()["max_results_applied"] == 25
    assert len(auth.provider.calls) == 2
    assert [call.page_size for call in auth.provider.calls] == [20, 5]
    assert "cap_note" in response.json()


def test_pagination_stops_at_one_hundred(auth):
    auth.provider = InfiniteProvider()
    response = _search(auth, max_results=100)
    assert response.status_code == 200, response.text
    assert response.json()["search"]["result_count"] == 100
    assert len(auth.provider.calls) == 5
    assert all(call.page_size == 20 for call in auth.provider.calls)


def test_duplicate_place_ids_are_removed(auth):
    first = NormalizedPlace(google_place_id="same", name="One", address="A", latitude=23.03, longitude=72.58, types=["hotel"])
    second = NormalizedPlace(google_place_id="other", name="Two", address="B", latitude=23.04, longitude=72.59, types=["hotel"])
    again = NormalizedPlace(google_place_id="same", name="One copy", address="A", latitude=23.03, longitude=72.58, types=["hotel"])
    auth.provider.pages = [[first, second], [again]]
    response = _search(auth, max_results=20)
    assert response.status_code == 200, response.text
    assert response.json()["search"]["result_count"] == 2


def test_duplicate_fallback_key_is_removed(auth):
    first = NormalizedPlace(
        google_place_id=None,
        name="City Gym",
        address="12 Road, Ahmedabad",
        latitude=23.02251,
        longitude=72.57141,
        types=["gym"],
    )
    second = NormalizedPlace(
        google_place_id=None,
        name="city  gym",
        address="12 road ahmedabad",
        latitude=23.02254,
        longitude=72.57144,
        types=["gym"],
    )
    auth.provider.pages = [[first, second]]
    response = _search(auth, category="Gym", location="Navrangpura")
    assert response.status_code == 200, response.text
    assert response.json()["search"]["result_count"] == 1


def test_filters_applied_before_persist(auth):
    low = NormalizedPlace(google_place_id="low", name="Low", rating=2.0, review_count=1, latitude=23.03, longitude=72.58, types=["hotel"])
    high = NormalizedPlace(
        google_place_id="high",
        name="High",
        rating=4.9,
        review_count=40,
        latitude=23.04,
        longitude=72.59,
        types=["hotel"],
        website="https://high.example",
        phone="079111",
    )
    auth.provider.pages = [[low, high]]
    response = _search(auth, min_rating=4, min_reviews=10, has_website=True)
    assert response.status_code == 200, response.text
    assert response.json()["search"]["result_count"] == 1
    assert response.json()["results"][0]["name"] == "High"


def test_zero_results_message(auth):
    auth.provider.pages = [[]]
    response = _search(auth, category="School", location="Ahmedabad")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["search"]["result_count"] == 0
    assert body["message"] == "No places found for this search."
    assert body["results"] == []


def test_location_not_found_and_quota(auth):
    auth.geocoder.error = LocationNotFoundError()
    missing = _search(auth, location="Not A Real Place xyz")
    assert missing.status_code == 422
    assert missing.json()["error_type"] == "location_not_found"
    assert "could not resolve" in missing.json()["detail"].lower()
    assert auth.provider.calls == []

    auth.geocoder.error = None
    auth.provider.error = GoogleServiceError("quota_exceeded", QUOTA_MESSAGE, 429, 429)
    quota = _search(auth, category="Hospital", location="Surat")
    assert quota.status_code == 429
    assert quota.json()["detail"] == QUOTA_MESSAGE
    assert quota.json()["error_type"] == "quota_exceeded"


def test_rerun_and_history_round_trip(auth):
    created = _search(auth, category="College", location="Gandhinagar")
    search_id = created.json()["search"]["id"]
    auth.provider.calls.clear()
    auth.geocoder.calls.clear()
    rerun = auth.client.post(f"/api/search/{search_id}/rerun", headers=auth.headers)
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["search"]["id"] != search_id
    assert rerun.json()["search"]["category"] == "College"
    assert auth.geocoder.calls == ["Gandhinagar"]
    history = auth.client.get("/api/history", headers=auth.headers)
    assert history.status_code == 200
    assert history.json()["total"] >= 2
    deleted = auth.client.delete(f"/api/history/{search_id}", headers=auth.headers)
    assert deleted.status_code == 204
    missing = auth.client.get(f"/api/search/{search_id}", headers=auth.headers)
    assert missing.status_code == 404
