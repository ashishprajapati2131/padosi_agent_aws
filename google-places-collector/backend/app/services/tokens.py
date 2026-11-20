from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings
from app.models import User


def create_token(user: User, token_type: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if token_type == "refresh":
        expires = now + timedelta(days=settings.jwt_refresh_days)
    else:
        expires = now + timedelta(minutes=settings.jwt_access_minutes)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": expires,
    }
    return jwt.encode(payload, settings.jwt_signing_key, algorithm="HS256")


def decode_token(token: str, expected_type: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_signing_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("token type")
    return payload
