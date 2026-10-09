"""Agent-controlled public profile section switches.

Same fields the website toggles at POST /agent/update-visibility/.
Profile-wide and directory-card switches stay admin-only.
"""
from fastapi import HTTPException, status

from fastapi_app.models.agent_profile import AgentProfile

VISIBILITY_FIELDS = (
    "show_certificates",
    "show_achievements",
    "show_reviews",
    "show_experience",
    "show_claims_stats",
    "show_client_base",
    "show_ratings",
    "show_languages",
    "show_gallery",
    "show_contact_info",
    "show_social_links",
)


def visibility_snapshot(profile) -> dict:
    return {name: bool(getattr(profile, name)) for name in VISIBILITY_FIELDS}


def get_visibility(db, agent_id: int) -> dict:
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent_id).first()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found",
        )
    return visibility_snapshot(profile)


def update_visibility(db, agent_id: int, field: str, value: bool) -> dict:
    if field not in VISIBILITY_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid field",
        )
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent_id).first()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found",
        )
    setattr(profile, field, bool(value))
    db.commit()
    return visibility_snapshot(profile)
