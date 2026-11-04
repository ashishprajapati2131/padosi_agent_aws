"""Public \"Licensed\" badge visibility (IRDAI insurance licence). Display-only."""
from __future__ import annotations

import datetime


def _profile_for_agent(agent):
    try:
        return agent.profile
    except Exception:
        return None


def insurance_license_badge_visible(agent) -> bool:
    """
    True when the agent may show the public Licensed (IRDAI) badge:
    admin irdai flag and/or a license number, and licence not past valid_till.
    """
    profile = _profile_for_agent(agent)
    badge_raw = (getattr(agent, "badge", None) or "").lower()
    badge_tokens = {b.strip() for b in badge_raw.split(",") if b.strip()}
    has_flag = "irdai" in badge_tokens

    license_number = ""
    valid_till = None
    if profile is not None:
        license_number = (getattr(profile, "license_number", None) or "").strip()
        valid_till = getattr(profile, "license_valid_till", None)

    if not has_flag and not license_number:
        return False

    if valid_till is not None:
        today = datetime.date.today()
        if valid_till < today:
            return False

    return True
