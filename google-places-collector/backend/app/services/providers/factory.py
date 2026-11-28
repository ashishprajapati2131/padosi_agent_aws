from __future__ import annotations

from app.config import get_settings
from app.services.google_places import GooglePlacesClient
from app.services.providers.base import PlaceProvider
from app.services.providers.google import GooglePlacesProvider


def get_provider() -> PlaceProvider:
    name = (get_settings().place_provider or "google").strip().lower()
    if name == "google":
        return GooglePlacesProvider(GooglePlacesClient())
    raise RuntimeError("The configured place provider is not available.")
