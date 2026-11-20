"""Show whether the server key is configured.

This script does not call Google unless you pass --live, and --live still
refuses to run when GOOGLE_MAPS_API_KEY is empty.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Google Places configuration")
    parser.add_argument("--live", action="store_true", help="Geocode one fixed address if a key is set")
    args = parser.parse_args()
    settings = get_settings()
    configured = bool((settings.google_maps_api_key or "").strip())
    print(f"google_configured={str(configured).lower()}")
    print(f"field_mode={settings.google_places_field_mode}")
    if not configured:
        print("GOOGLE_MAPS_API_KEY is not set. Live connectivity was not checked.")
        return 0
    if not args.live:
        print("Key is set. Pass --live to run one Geocoding request. This command did not call Google.")
        return 0
    from app.services.geocoding import GeocodingService

    result = GeocodingService().geocode("Ahmedabad")
    print(f"formatted_address={result.formatted_address}")
    print(f"latitude={result.latitude}")
    print(f"longitude={result.longitude}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
