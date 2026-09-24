from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.services.lock_unlock_service import LockUnlockService

router = APIRouter(
    prefix="/v1/agents/visibility",
    tags=["Visibility & Profile Toggles"]
)

PROFILE_TOGGLE_FIELDS = [
    'show_certificates', 'show_achievements', 'show_reviews',
    'show_experience', 'show_claims_stats', 'show_client_base', 'show_ratings',
    'show_languages', 'show_gallery', 'show_contact_info', 'show_social_links'
]


class VisibilityToggleRequest(BaseModel):
    field: str
    value: bool


def _toggle_value(profile, field: str) -> bool:
    if not profile:
        return True
    return bool(getattr(profile, field, True))


@router.get("")
def get_visibility_status(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get profile section visibility states and discovery visibility flags.
    """
    lock_service = LockUnlockService(db)
    access_map = lock_service.get_feature_access_map(current_agent)
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == current_agent.id).first()

    return {
        "success": True,
        "discovery_features": {
            "is_listed_in_directory": not access_map.get("agent_directory_visibility", {}).get("is_locked", False),
            "visibility_aio": not access_map.get("visibility_aio", {}).get("is_locked", False),
            "visibility_geo": not access_map.get("visibility_geo", {}).get("is_locked", False),
            "visibility_seo": not access_map.get("visibility_seo", {}).get("is_locked", False),
            "visibility_priority_ranking": not access_map.get("visibility_priority_ranking", {}).get("is_locked", False),
        },
        "profile_toggles": {
            field: _toggle_value(profile, field) for field in PROFILE_TOGGLE_FIELDS
        }
    }

@router.post("/toggle")
def toggle_visibility(
    payload: VisibilityToggleRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Toggle visibility of a specific profile section.
    Guarded by respective feature lock permissions.
    """
    if payload.field not in PROFILE_TOGGLE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid field. Allowed fields are: {', '.join(PROFILE_TOGGLE_FIELDS)}"
        )

    lock_service = LockUnlockService(db)
    if payload.value:
        if payload.field == 'show_certificates':
            lock_service.require_feature_unlocked(current_agent, "edit_profile_certifications")
        elif payload.field in ('show_achievements', 'show_gallery'):
            lock_service.require_feature_unlocked(current_agent, "upload_achievements")
        elif payload.field == 'show_social_links':
            lock_service.require_feature_unlocked(current_agent, "edit_profile_social_media")
        elif payload.field == 'show_reviews':
            lock_service.require_feature_unlocked(current_agent, "view_reviews")

    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == current_agent.id).first()
    if not profile:
        profile = AgentProfile(agent_id=current_agent.id)
        db.add(profile)

    setattr(profile, payload.field, bool(payload.value))
    db.commit()
    db.refresh(profile)

    saved_value = _toggle_value(profile, payload.field)
    return {
        "success": True,
        "field": payload.field,
        "value": saved_value,
        "message": f"Visibility for {payload.field} updated successfully."
    }
