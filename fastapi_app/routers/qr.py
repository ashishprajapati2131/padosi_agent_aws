from fastapi import APIRouter, Depends, HTTPException, status
from urllib.parse import quote
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.services.lock_unlock_service import LockUnlockService
from fastapi_app.config import settings

router = APIRouter(
    prefix="/api/v1/agents/qr",
    tags=["QR Codes & Reviews"]
)

@router.get("/tools")
def get_qr_tools(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get QR code links, targets, and share buttons for Profile, Card, and Reviews.
    """
    lock_service = LockUnlockService(db)
    access_map = lock_service.get_feature_access_map(current_agent)
    
    qr_access = not access_map.get("qr_codes", {}).get("is_locked", False)
    allow_download = not access_map.get("qr_poster_download", {}).get("is_locked", False)

    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == current_agent.id).first()
    slug = (profile.slug if profile and profile.slug else '') or getattr(current_agent, 'agent_slug', '') or str(current_agent.id)
    app_url = settings.APP_URL.rstrip('/')

    labels = {
        'profile': 'Profile QR Code',
        'card': 'Visiting Card QR Code',
        'reviews': 'Client Review QR Code'
    }

    items = []
    for qr_type, label in labels.items():
        if qr_type == 'reviews':
            target = f"{app_url}/profile/{slug}/review/"
        elif qr_type == 'card':
            target = f"{app_url}/card/{slug}/"
        else:
            target = f"{app_url}/profile/{slug}/"

        whatsapp_msg = f"I'm on PadosiAgent. Scan my {label}: {target}"
        items.append({
            "type": qr_type,
            "label": label,
            "target_url": target,
            "preview_url": f"{app_url}/agent/qr/{qr_type}.png",
            "download_url": f"{app_url}/agent/qr/{qr_type}/download/",
            "whatsapp_url": f"https://api.whatsapp.com/send?text={quote(whatsapp_msg)}",
            "facebook_url": f"https://www.facebook.com/sharer/sharer.php?u={quote(target)}"
        })

    return {
        "success": True,
        "service_enabled": qr_access,
        "allow_download": allow_download,
        "items": items,
        "features_access": {
            "qr_codes": access_map.get("qr_codes"),
            "qr_poster_download": access_map.get("qr_poster_download")
        }
    }
