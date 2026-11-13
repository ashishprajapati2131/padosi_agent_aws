"""In-memory provider and geocoder. Tests never call Google."""

from __future__ import annotations

from app.services.errors import AppError
from app.services.normalized import GeocodeResult, NormalizedPlace, ProviderSearchPage
from app.services.providers.google import normalize_place


class FakeGeocoder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None
        self.result = GeocodeResult(
            latitude=23.0225,
            longitude=72.5714,
            formatted_address="Ahmedabad, Gujarat, India",
            status_code=200,
            duration_ms=4,
        )

    def geocode(self, location: str) -> GeocodeResult:
        self.calls.append(location)
        if self.error:
            raise self.error
        return self.result


class ScriptedProvider:
    def __init__(self, pages: list[list] | None = None) -> None:
        self.pages = pages if pages is not None else [[sample_place()]]
        self.calls = []
        self.error: Exception | None = None

    def search(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        index = len(self.calls) - 1
        batch = self.pages[index] if index < len(self.pages) else []
        token = f"token-{index + 1}" if index < len(self.pages) - 1 else None
        places = [_as_place(item) for item in batch]
        operation = "searchNearby" if request.mode == "nearby" else "searchText"
        return ProviderSearchPage(
            places=places,
            next_page_token=token,
            status_code=200,
            duration_ms=6,
            operation=operation,
            result_count=len(places),
        )

    def get_details(self, place_id: str, field_mode: str) -> NormalizedPlace:
        return normalize_place(
            {
                "id": place_id,
                "displayName": {"text": "Detail Place"},
                "formattedAddress": "Ahmedabad",
                "regularOpeningHours": {"weekdayDescriptions": ["Monday: 9:00 AM – 5:00 PM"], "openNow": True},
            }
        )


class InfiniteProvider:
    def __init__(self) -> None:
        self.calls = []

    def search(self, request):
        self.calls.append(request)
        start = len(self.calls) * 1000
        places = [
            NormalizedPlace(
                google_place_id=f"id-{start + index}",
                name=f"Place {start + index}",
                address="Ahmedabad",
                latitude=23.03,
                longitude=72.58,
                rating=4.2,
                review_count=12,
                types=["point_of_interest"],
            )
            for index in range(request.page_size)
        ]
        return ProviderSearchPage(
            places=places,
            next_page_token=f"tok-{len(self.calls)}",
            status_code=200,
            duration_ms=1,
            operation="searchText",
            result_count=len(places),
        )

    def get_details(self, place_id: str, field_mode: str) -> NormalizedPlace:
        raise AssertionError("details were not expected")


def sample_place(**overrides) -> dict:
    payload = {
        "id": "place-hotel-1",
        "displayName": {"text": "River Hotel"},
        "formattedAddress": "Ashram Road, Ahmedabad",
        "location": {"latitude": 23.03, "longitude": 72.58},
        "types": ["hotel", "lodging"],
        "nationalPhoneNumber": "0790000000",
        "websiteUri": "https://example.com/hotel",
        "rating": 4.4,
        "userRatingCount": 120,
        "businessStatus": "OPERATIONAL",
        "googleMapsUri": "https://maps.google.com/?cid=1",
    }
    payload.update(overrides)
    return payload


def _as_place(item) -> NormalizedPlace:
    if isinstance(item, NormalizedPlace):
        return item
    if isinstance(item, dict):
        return normalize_place(item)
    raise TypeError("unsupported place fixture")


def raise_if(error: AppError | None) -> None:
    if error:
        raise error
