import json

import httpx
import pytest
from app.services.errors import QUOTA_MESSAGE, GoogleServiceError
from app.services.geocoding import GeocodingService
from app.services.google_places import GooglePlacesClient, field_mask_for
from app.services.providers.google import GooglePlacesProvider, normalize_place
from app.utils.logger import log_event


def test_field_masks_for_each_mode():
    minimal = field_mask_for("minimal", "searchText")
    assert "places.id" in minimal.split(",")
    assert "places.displayName" in minimal
    assert "places.location" in minimal
    assert "places.formattedAddress" in minimal
    assert "places.types" in minimal
    assert "nextPageToken" in minimal
    assert "places.rating" not in minimal
    assert "places.websiteUri" not in minimal
    assert "regularOpeningHours" not in minimal

    standard = field_mask_for("standard", "searchText")
    for field in (
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "places.googleMapsUri",
        "nextPageToken",
    ):
        assert field in standard
    assert "regularOpeningHours" not in standard

    detailed = field_mask_for("detailed", "searchText")
    assert "places.regularOpeningHours" in detailed

    details = field_mask_for("detailed", "placeDetails")
    assert "places." not in details
    assert "nextPageToken" not in details
    assert "regularOpeningHours" in details.split(",")
    assert "id" in details.split(",")

    nearby = field_mask_for("standard", "searchNearby")
    assert "nextPageToken" not in nearby
    assert "places.rating" in nearby


def test_text_search_request_shape(caplog):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["mask"] = request.headers.get("X-Goog-FieldMask")
        seen["key_header"] = request.headers.get("X-Goog-Api-Key")
        seen["body"] = json.loads(request.content.decode())
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"places": [], "nextPageToken": None})

    client = GooglePlacesClient(
        api_key="test-key",
        timeout=2,
        max_retries=2,
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    import logging

    logger = logging.getLogger("places")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    try:
        provider = GooglePlacesProvider(client)
        from app.services.normalized import ProviderSearchRequest

        page = provider.search(
            ProviderSearchRequest(
                mode="text",
                text_query="Hotel Ahmedabad",
                included_types=None,
                latitude=23.0225,
                longitude=72.5714,
                radius_meters=5000,
                language="en",
                page_token=None,
                page_size=20,
                field_mode="standard",
            )
        )
    finally:
        logger.removeHandler(caplog.handler)

    assert page.result_count == 0
    assert seen["url"].endswith("/places:searchText")
    assert seen["body"]["textQuery"] == "Hotel Ahmedabad"
    assert seen["body"]["pageSize"] == 20
    assert seen["body"]["languageCode"] == "en"
    assert seen["body"]["locationBias"]["circle"]["center"] == {"latitude": 23.0225, "longitude": 72.5714}
    assert seen["body"]["locationBias"]["circle"]["radius"] == 5000.0
    assert "key" not in seen["body"]
    assert seen["key_header"] == "test-key"
    assert "places.rating" in seen["mask"]
    assert "places.regularOpeningHours" not in seen["mask"]
    assert "test-key" not in caplog.text
    assert "google_places_request" in caplog.text
    assert "google_places_response" in caplog.text


def test_nearby_request_uses_included_type_and_meters():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode())
        seen["url"] = str(request.url)
        seen["mask"] = request.headers.get("X-Goog-FieldMask")
        return httpx.Response(200, json={"places": []})

    client = GooglePlacesClient(api_key="test-key", timeout=2, max_retries=0, transport=httpx.MockTransport(handler))
    provider = GooglePlacesProvider(client)
    from app.services.normalized import ProviderSearchRequest

    provider.search(
        ProviderSearchRequest(
            mode="nearby",
            text_query=None,
            included_types=["petrol_pump"],
            latitude=23.0,
            longitude=72.5,
            radius_meters=1500,
            language="en",
            page_token=None,
            page_size=10,
            field_mode="minimal",
        )
    )
    assert seen["url"].endswith("/places:searchNearby")
    assert seen["body"]["includedTypes"] == ["petrol_pump"]
    assert seen["body"]["maxResultCount"] == 10
    assert seen["body"]["locationRestriction"]["circle"]["radius"] == 1500.0
    assert "nextPageToken" not in seen["mask"]
    assert "places.rating" not in seen["mask"]


def test_retries_only_transient_statuses():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": {"code": 503, "status": "UNAVAILABLE", "message": "later"}})
        return httpx.Response(200, json={"places": [{"id": "ok", "displayName": {"text": "Ok"}}]})

    client = GooglePlacesClient(
        api_key="test-key",
        timeout=2,
        max_retries=2,
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    payload = client.search_text({"textQuery": "Gym Navrangpura"}, field_mask_for("minimal", "searchText"))
    assert calls["n"] == 3
    assert payload["places"][0]["id"] == "ok"


@pytest.mark.parametrize(
    ("status", "body", "error_type", "message_part"),
    [
        (429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}}, "quota_exceeded", QUOTA_MESSAGE),
        (400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "API key not valid. Please pass a valid API key."}}, "invalid_api_key", "invalid"),
        (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Places API (New) has not been used in project 1"}}, "permission_denied", "not enabled"),
        (403, {"error": {"code": 403, "status": "PERMISSION_DENIED", "message": "Billing to the project is disabled"}}, "billing_disabled", "billing"),
        (400, {"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "includedTypes is invalid"}}, "invalid_request", "Nearby search"),
    ],
)
def test_error_mapping(status, body, error_type, message_part):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, json=body)

    client = GooglePlacesClient(
        api_key="test-key",
        timeout=2,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    operation = "searchNearby" if "includedTypes" in json.dumps(body) else "searchText"
    with pytest.raises(GoogleServiceError) as caught:
        if operation == "searchNearby":
            client.search_nearby({}, field_mask_for("standard", "searchNearby"))
        else:
            client.search_text({}, field_mask_for("standard", "searchText"))
    assert calls["n"] == 1
    assert caught.value.error_type == error_type
    assert message_part.lower() in caught.value.message.lower()
    assert "test-key" not in caught.value.message


def test_timeout_and_missing_key():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = GooglePlacesClient(
        api_key="test-key",
        timeout=1,
        max_retries=0,
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(GoogleServiceError) as caught:
        client.search_text({}, "places.id")
    assert caught.value.error_type == "timeout"
    assert "test-key" not in caught.value.message

    empty = GooglePlacesClient(api_key="", timeout=1, max_retries=0, sleep=lambda _seconds: None)
    with pytest.raises(GoogleServiceError) as missing:
        empty.search_text({}, "places.id")
    assert missing.value.error_type == "invalid_api_key"


def test_geocode_zero_results_and_success():
    def missing(request: httpx.Request) -> httpx.Response:
        assert "key=" in str(request.url)
        assert "Ahmedabad" in str(request.url)
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    service = GeocodingService(api_key="test-key", timeout=2, max_retries=0, transport=httpx.MockTransport(missing))
    from app.services.errors import LocationNotFoundError

    with pytest.raises(LocationNotFoundError):
        service.geocode("Ahmedabad")

    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "OK",
                "results": [
                    {
                        "formatted_address": "Surat, Gujarat, India",
                        "geometry": {"location": {"lat": 21.17, "lng": 72.83}},
                    }
                ],
            },
        )

    found = GeocodingService(api_key="test-key", timeout=2, max_retries=0, transport=httpx.MockTransport(ok))
    result = found.geocode("Surat")
    assert result.formatted_address.startswith("Surat")
    assert result.latitude == 21.17


def test_normalize_does_not_invent_fields():
    place = normalize_place({"id": "abc", "displayName": {"text": "Cafe"}})
    assert place.name == "Cafe"
    assert place.google_place_id == "abc"
    assert place.phone is None
    assert place.rating is None
    assert place.address is None
    assert place.website is None
    assert place.opening_hours is None


def test_log_redacts_key_material():
    import logging

    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger("places")
    handler = ListHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        log_event("info", "google_places_request", operation="searchText", note="AIzaREDACTME", api_key="should-drop")
    finally:
        logger.removeHandler(handler)
    blob = " ".join(records)
    assert "AIzaREDACTME" not in blob
    assert "should-drop" not in blob
    assert "google_places_request" in blob
