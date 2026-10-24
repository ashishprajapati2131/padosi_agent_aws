from __future__ import annotations

import bcrypt

from app.config import get_settings

_dummy_by_rounds: dict[int, str] = {}


def hash_password(password: str) -> str:
    rounds = get_settings().bcrypt_rounds
    digest = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds))
    return digest.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def dummy_verify(password: str) -> None:
    """Spend a comparable bcrypt check when the email does not exist."""
    rounds = get_settings().bcrypt_rounds
    if rounds not in _dummy_by_rounds:
        _dummy_by_rounds[rounds] = hash_password("dummy-password-not-used")
    verify_password(password, _dummy_by_rounds[rounds])
