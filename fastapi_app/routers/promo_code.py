from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.registration import PromoCodeValidateRequest, PromoCodeValidateResponse
from app.repositories.promo_code_repository import PromoCodeRepository
from app.utils.auth import create_promo_validation_token

router = APIRouter(prefix="/api/v1/promo-code", tags=["Promo Code Validation"])

@router.post("/validate", response_model=PromoCodeValidateResponse, status_code=status.HTTP_200_OK)
def validate_promo_code_endpoint(
    request: PromoCodeValidateRequest,
    db: Session = Depends(get_db)
):
    promo_code = request.promo_code.strip() if request.promo_code else ""
    if not promo_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Promo code is required"
        )

    promo_repo = PromoCodeRepository(db)
    promo = promo_repo.get_by_code(promo_code)

    if promo and promo.is_valid():
        token = create_promo_validation_token(promo.code, promo.id)
        return PromoCodeValidateResponse(
            success=True,
            message="Promo code validated successfully.",
            promo_valid=True,
            token=token,
            expires_in=1200
        )

    return PromoCodeValidateResponse(
        success=False,
        message="Invalid or expired promo code."
    )
