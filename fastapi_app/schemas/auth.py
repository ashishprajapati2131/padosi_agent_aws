from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional, Dict, Any, Literal

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    success: bool
    message: str
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None

class AgentMeResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None

class LogoutResponse(BaseModel):
    success: bool
    message: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    login_type: Literal["agent", "distributor"]

class ForgotPasswordResponse(BaseModel):
    success: bool
    message: str

from typing import Optional, Literal

class ResetPasswordRequest(BaseModel):
    token: Optional[str] = None
    email: EmailStr
    password: str
    password_confirmation: str
    login_type: Literal["agent", "distributor"]


    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number.")
        if not any(not c.isalnum() for c in v):
            raise ValueError("The password must contain at least one special character.")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> 'ResetPasswordRequest':
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        return self

class ResetPasswordResponse(BaseModel):
    success: bool
    message: str
