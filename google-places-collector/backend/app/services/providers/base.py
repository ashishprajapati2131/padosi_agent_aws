"""Place provider contract. New sources implement this without rewriting search or the UI."""

from __future__ import annotations

from typing import Protocol

from app.services.normalized import NormalizedPlace, ProviderSearchPage, ProviderSearchRequest


class PlaceProvider(Protocol):
    def search(self, request: ProviderSearchRequest) -> ProviderSearchPage:
        """Run one page of a place search. Pagination tokens stay inside the backend."""

    def get_details(self, place_id: str, field_mode: str) -> NormalizedPlace:
        """Load one place. Missing fields stay null."""
