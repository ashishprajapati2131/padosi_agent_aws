from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.schemas.digital_card import (
    PublicDigitalCardResponse,
    DigitalCardLeadRequest,
    DigitalCardLeadResponse,
)
from fastapi_app.services.digital_card_service import DigitalCardService

router = APIRouter(
    prefix="/v1/public/digital-card",
    tags=["Public Digital Visiting Card"],
)


def get_service(db: Session = Depends(get_db)) -> DigitalCardService:
    return DigitalCardService(db)


@router.get("/{slug}", response_model=PublicDigitalCardResponse)
def get_public_digital_card(
    slug: str,
    service: DigitalCardService = Depends(get_service),
):
    """Public digital visiting card JSON (feature flag + visibility + policies)."""
    return service.get_public_card(slug)


@router.get("/{slug}/vcard")
def get_public_vcard(
    slug: str,
    service: DigitalCardService = Depends(get_service),
):
    content, filename = service.build_vcard(slug)
    return Response(
        content=content,
        media_type="text/vcard; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/{slug}/qr.png")
def get_public_card_qr(
    slug: str,
    service: DigitalCardService = Depends(get_service),
):
    png = service.build_qr_png(slug)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug) or "card"
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'inline; filename="QR-{safe}-card.png"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.post("/{slug}/leads", response_model=DigitalCardLeadResponse)
def submit_digital_card_lead(
    slug: str,
    payload: DigitalCardLeadRequest,
    request: Request,
    service: DigitalCardService = Depends(get_service),
):
    """Lead form submit — same interaction_type/source_page as Django digital card."""
    client_ip = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    return service.submit_lead(slug, payload.model_dump(), client_ip=client_ip)
