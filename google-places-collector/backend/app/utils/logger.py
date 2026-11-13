"""Structured JSON logs. Never include API keys, passwords, or raw upstream bodies."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOGGER_NAME = "places"
_SECRET_MARKERS = ("AIza", "api_key", "password", "secret", "authorization", "Bearer ")


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        lowered = value.lower()
        if any(marker.lower() in lowered for marker in _SECRET_MARKERS):
            return "[redacted]"
        if len(value) > 500:
            return value[:500]
        return value
    if isinstance(value, dict):
        return {str(key): _sanitize(item) for key, item in value.items() if not _blocked_key(str(key))}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:50]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def _blocked_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {"api_key", "authorization", "password", "jwt", "jwt_secret", "google_maps_api_key"}


def setup_logging(level: str = "INFO") -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def log_event(level: str, event: str, **fields: Any) -> None:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        setup_logging()
    payload = {
        "time": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
    }
    for key, value in fields.items():
        if _blocked_key(key):
            continue
        payload[key] = _sanitize(value)
    message = json.dumps(payload, default=str, separators=(",", ":"))
    getattr(logger, level.lower(), logger.info)(message)
