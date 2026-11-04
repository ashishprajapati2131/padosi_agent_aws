"""IRDAI license active/expired checks (naive dates — USE_TZ=False)."""
import datetime


def _as_date(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def is_irdai_license_active(profile) -> bool:
    if not profile or not getattr(profile, "license_number", None):
        return False
    valid_till = _as_date(getattr(profile, "license_valid_till", None))
    if not valid_till:
        return True
    return valid_till >= datetime.date.today()


def is_irdai_license_expired(profile) -> bool:
    if not profile or not getattr(profile, "license_number", None):
        return False
    valid_till = _as_date(getattr(profile, "license_valid_till", None))
    if not valid_till:
        return False
    return valid_till < datetime.date.today()


def compose_badge_csv(agent) -> str:
    """Public badge keys for cards/compare, respecting license expiry."""
    raw = (getattr(agent, "badge", None) or "").strip().lower()
    keys = [b.strip() for b in raw.split(",") if b.strip() and b.strip() != "none"]
    profile = getattr(agent, "profile", None)
    active_irdai = is_irdai_license_active(profile)
    has_irdai_key = "irdai" in keys
    if active_irdai and not has_irdai_key:
        keys.append("irdai")
    if not active_irdai and has_irdai_key:
        keys = [k for k in keys if k != "irdai"]
    if not keys:
        return "none"
    return ",".join(keys)
