from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any
import html

class RegistrationBasicRequest(BaseModel):
    fullname: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    mobile: str = Field(..., pattern=r'^\d{10}$')
    agent_pincode: str = Field(..., pattern=r'^\d{6}$')
    experience_range: Optional[str] = None
    client_base: Optional[str] = None

    @field_validator("fullname", "experience_range", "client_base", "promo_code", mode="before")
    @classmethod
    def sanitize_strings(cls, v):
        if v is not None and isinstance(v, str):
            return html.escape(v.strip())
        return v
    segments: List[str] = []
    investment_types: List[str] = []
    
    # Optional fields passed in payload that we might ignore but accept
    user_types: List[str] = ["insurance_agent"]
    promo_code: Optional[str] = None
    promo_token: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class RegistrationBasicResponse(BaseModel):
    success: bool
    agent_id: int
    message: str
    name: Optional[str] = None
    email: Optional[str] = None
    token: Optional[str] = None
    jwt_token: Optional[str] = None
    is_payment_done: bool = False


# Promo Code Validation schemas
class PromoCodeValidateRequest(BaseModel):
    promo_code: str

class PromoCodeValidateResponse(BaseModel):
    success: bool
    message: str
    promo_valid: Optional[bool] = None
    token: Optional[str] = None
    expires_in: Optional[int] = None


# Pricing request
class PricingRequest(BaseModel):
    agent_id: int


# Plan details schemas
class PlanDetails(BaseModel):
    name: str
    base_amount: float
    gst_amount: float
    total_amount: float
    original_amount: float
    discount_amount: float
    discounted_amount: float
    applied_promo_code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    currency: str = "INR"

class PricingResponse(BaseModel):
    success: bool
    plans: Dict[str, PlanDetails]
    applied_promo: Optional[str] = None
    jwt_token: Optional[str] = None


# Order requests
class OrderRequest(BaseModel):
    agent_id: int
    plan_type: str  # basic, professional, free_trial
    plan_name: Optional[str] = None

class OrderResponse(BaseModel):
    success: bool
    order_id: str
    amount: float  # In Rupees
    key: str
    agent_id: int
    name: str
    email: str
    plan_amount: float
    total_amount: float
    test_payment: bool
    jwt_token: Optional[str] = None


# Payment success request
class PaymentSuccessRequest(BaseModel):
    agent_id: int
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    plan_type: Optional[str] = None

class PaymentSuccessResponse(BaseModel):
    success: bool
    message: str
    redirect_url: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
