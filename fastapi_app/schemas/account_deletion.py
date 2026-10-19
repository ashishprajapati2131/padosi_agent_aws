from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
import re


class RequestDeletionOtpSchema(BaseModel):
    fullname: str = Field(..., min_length=2, max_length=150, description="Full Name of the account holder")
    email: EmailStr = Field(..., description="Registered Email ID")
    mobile: str = Field(..., min_length=10, max_length=15, description="Registered Mobile Number")
    pan_number: str = Field(..., min_length=10, max_length=10, description="Permanent Account Number (PAN)")
    reason: str = Field(..., min_length=3, max_length=200, description="Reason for deletion")
    comments: Optional[str] = Field(None, max_length=1000, description="Why delete your account detail / feedback")

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        clean = re.sub(r"[^\d]", "", v)
        if len(clean) != 10:
            raise ValueError("Mobile number must be exactly 10 digits")
        return clean

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$", v_upper):
            raise ValueError("Please enter a valid 10-character PAN number (e.g. ABCDE1234F)")
        return v_upper


class VerifyDeletionOtpSchema(BaseModel):
    reference_id: str = Field(..., min_length=5, max_length=50)
    email: EmailStr = Field(...)
    otp: str = Field(..., min_length=4, max_length=8)


class DeletionResponseSchema(BaseModel):
    success: bool
    message: str
    reference_id: Optional[str] = None
    status: Optional[str] = None


class DeletionStatusDetailSchema(BaseModel):
    success: bool
    message: str
    reference_id: str
    status: str
    status_display: str
    is_verified: bool
    fullname: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    submitted_at: Optional[str] = None
    processed_at: Optional[str] = None
    reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    admin_notes: Optional[str] = None

