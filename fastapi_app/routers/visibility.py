from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.services.lock_unlock_service import LockUnlockService

router = APIRouter(
    prefix="/api/v1/agents/visibility",
    tags=["Visibility & Profile Toggles"]
)

class VisibilityToggleRequest(BaseModel):
    field: str
    value: bool

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
            "show_certificates": getattr(profile, 'show_certificates', True) if profile else True,
            "show_achievements": getattr(profile, 'show_achievements', True) if profile else True,
            "show_reviews": getattr(profile, 'show_reviews', True) if profile else True,
            "show_experience": getattr(profile, 'show_experience', True) if profile else True,
            "show_claims_stats": getattr(profile, 'show_claims_stats', True) if profile else True,
            "show_client_base": getattr(profile, 'show_client_base', True) if profile else True,
            "show_ratings": getattr(profile, 'show_ratings', True) if profile else True,
            "show_languages": getattr(profile, 'show_languages', True) if profile else True,
            "show_gallery": getattr(profile, 'show_gallery', True) if profile else True,
            "show_contact_info": getattr(profile, 'show_contact_info', True) if profile else True,
            "show_social_links": getattr(profile, 'show_social_links', True) if profile else True,
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
    valid_fields = [
        'show_certificates', 'show_achievements', 'show_reviews',
        'show_experience', 'show_claims_stats', 'show_client_base', 'show_ratings',
        'show_languages', 'show_gallery', 'show_contact_info', 'show_social_links'
    ]
    if payload.field not in valid_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid field. Allowed fields are: {', '.join(valid_fields)}"
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

    setattr(profile, payload.field, 1 if payload.value else 0)
    db.commit()

    return {
        "success": True,
        "field": payload.field,
        "value": payload.value,
        "message": f"Visibility for {payload.field} updated successfully."
    }
