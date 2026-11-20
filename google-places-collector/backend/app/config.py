"""Runtime configuration. Secrets stay here — never in the frontend bundle."""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILES = (
    "google-places-collector/.env",
    ".env",
    "../.env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    google_maps_api_key: str = ""
    google_places_field_mode: str = "standard"
    place_provider: str = "google"
    database_url: str = "sqlite:///./places_dev.db"
    jwt_secret: str = ""
    jwt_access_minutes: int = 30
    jwt_refresh_days: int = 7
    max_results_per_search: int = 100
    max_searches_per_minute: int = 10
    max_searches_per_minute_ip: int = 20
    max_detail_requests_per_minute: int = 60
    google_api_timeout: float = 10
    google_api_max_retries: int = 2
    search_retention_days: int = 90
    bulk_max_rows: int = 25
    bulk_concurrency: int = 1
    log_level: str = "INFO"
    environment: str = "development"
    admin_email: str = ""
    admin_password: str = ""
    cors_origins: str = "http://localhost:5173"
    bcrypt_rounds: int = 12
    storage_disabled_fields: str = ""
    export_disabled_fields: str = ""
    export_field_flags: str = ""

    @field_validator("google_places_field_mode")
    @classmethod
    def _field_mode(cls, value: str) -> str:
        mode = (value or "standard").strip().lower()
        if mode not in {"minimal", "standard", "detailed"}:
            raise ValueError("GOOGLE_PLACES_FIELD_MODE must be minimal, standard, or detailed")
        return mode

    @field_validator("bulk_concurrency", mode="before")
    @classmethod
    def _bulk_concurrency(cls, value: object) -> int:
        try:
            number = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 1
        return max(1, min(number, 3))

    @field_validator("max_results_per_search", "bulk_max_rows", "google_api_max_retries")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        return max(0, int(value))

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def jwt_signing_key(self) -> str:
        secret = (self.jwt_secret or "").strip()
        if secret:
            return secret
        if self.environment.lower() == "production":
            raise RuntimeError("JWT_SECRET is required when ENVIRONMENT=production")
        return "dev-only-change-me"

    def _csv_set(self, raw: str) -> set[str]:
        return {part.strip() for part in (raw or "").split(",") if part.strip()}

    def storage_disabled(self) -> set[str]:
        # Place IDs are the dedup key and are permitted to be stored.
        return self._csv_set(self.storage_disabled_fields) - {"google_place_id"}

    def export_disabled(self) -> set[str]:
        disabled = self._csv_set(self.export_disabled_fields)
        raw = (self.export_field_flags or "").strip()
        if not raw:
            return disabled
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return disabled
        if isinstance(payload, dict):
            for key, enabled in payload.items():
                name = str(key).strip()
                if enabled is False:
                    disabled.add(name)
                elif enabled is True:
                    disabled.discard(name)
        return disabled


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
