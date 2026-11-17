from pydantic import BaseModel, Field
from typing import Optional


class RequestDeletionByPasswordSchema(BaseModel):
    """Logged-in agent confirms with their password. The account is not deleted here."""

    password: str = Field(..., min_length=1, max_length=200, description="Current account password")
    reason: Optional[str] = Field(None, max_length=200, description="Why the account should be closed")
    comments: Optional[str] = Field(None, max_length=1000)


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

