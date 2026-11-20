from fastapi import APIRouter, Depends, File, UploadFile, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.schemas.digital_card import (
    DigitalCardStudioStateResponse,
    DigitalCardUpdateRequest,
    DigitalCardUpdateResponse,
    DigitalCardShareResponse,
    InviteStudioResponse,
)
from fastapi_app.services.digital_card_service import DigitalCardService

router = APIRouter(
    prefix="/v1/agents/digital-card",
    tags=["Digital Visiting Card"],
)

invite_router = APIRouter(
    prefix="/v1/agents/invite-studio",
    tags=["Invite Studio"],
)

_IMAGE_MAX_BYTES = 5 * 1024 * 1024


async def _read_upload_capped(file: UploadFile, max_bytes: int) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            from fastapi import HTTPException

            raise HTTPException(status_code=400, detail="File too large (max 5MB).")
        chunks.append(chunk)
    return b"".join(chunks)


def get_service(db: Session = Depends(get_db)) -> DigitalCardService:
    return DigitalCardService(db)


@router.get("", response_model=DigitalCardStudioStateResponse)
def get_digital_card(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    """Full Digital Visiting Card studio state for the authenticated agent."""
    return service.get_studio_state(current_agent)


@router.put("", response_model=DigitalCardUpdateResponse)
@router.patch("", response_model=DigitalCardUpdateResponse)
def update_digital_card(
    payload: DigitalCardUpdateRequest,
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    """Update card text/settings (same fields as Django /agent/card/customize/)."""
    return service.update_card(current_agent, payload)


@router.post("/logo")
async def upload_agency_logo(
    file: UploadFile = File(...),
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    file_bytes = await _read_upload_capped(file, _IMAGE_MAX_BYTES)
    filename = file.filename or "logo.jpg"

    def _save():
        return service.upload_logo(current_agent, file_bytes, filename)

    return await run_in_threadpool(_save)


@router.delete("/logo")
def delete_agency_logo(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    return service.delete_logo(current_agent)


@router.post("/banner")
async def upload_card_banner(
    file: UploadFile = File(...),
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    file_bytes = await _read_upload_capped(file, _IMAGE_MAX_BYTES)
    filename = file.filename or "banner.jpg"

    def _save():
        return service.upload_banner(current_agent, file_bytes, filename)

    return await run_in_threadpool(_save)


@router.delete("/banner")
def delete_card_banner(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    return service.delete_banner(current_agent)


@router.get("/preview")
def preview_digital_card(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    """Resolved preview DTO for native mockup (studio + public merge)."""
    return service.get_preview(current_agent)


@router.get("/share", response_model=DigitalCardShareResponse)
def share_digital_card(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    return service.get_share_pack(current_agent)


@invite_router.get("", response_model=InviteStudioResponse)
def get_invite_studio(
    current_agent: Agent = Depends(get_current_agent),
    service: DigitalCardService = Depends(get_service),
):
    """Invite & Share Studio templates + rendered links for the agent."""
    return service.get_invite_studio(current_agent)
