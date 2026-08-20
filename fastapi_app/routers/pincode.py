from fastapi import APIRouter, Depends
from fastapi_app.schemas.pincode import PincodeResponse
from fastapi_app.services.pincode_service import PincodeService

router = APIRouter(
    prefix="/api/v1/pincode",
    tags=["Pincode Lookup"]
)

@router.get("/{pincode}", response_model=PincodeResponse)
def get_pincode_details(pincode: str):
    """
    Validate a 6-digit Indian pincode and return associated geographical data.
    """
    return PincodeService.validate_and_fetch_pincode(pincode)
