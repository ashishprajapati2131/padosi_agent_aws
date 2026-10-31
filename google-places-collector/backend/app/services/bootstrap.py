"""Seed the first admin from the environment. Never hard-code a password."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.services.passwords import hash_password
from app.utils.logger import log_event


def seed_admin(db: Session) -> None:
    settings = get_settings()
    email = (settings.admin_email or "").strip().lower()
    password = settings.admin_password or ""
    if not email or not password:
        return
    existing = db.query(User).filter(User.email == email).one_or_none()
    if existing is not None:
        return
    db.add(User(email=email, password_hash=hash_password(password), role="admin", is_active=True))
    db.commit()
    log_event("info", "admin_seeded", email=email)
