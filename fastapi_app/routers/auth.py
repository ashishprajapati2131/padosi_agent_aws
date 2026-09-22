from typing import Optional
from fastapi import APIRouter, Depends, status, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.schemas.auth import (
    LoginRequest, LoginResponse, AgentMeResponse, LogoutResponse,
    ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest, ResetPasswordResponse,
    PushTokenRequest, PushTokenResponse
)
from fastapi_app.services.auth_service import AuthService
from fastapi_app.services.password_reset_service import PasswordResetService
from fastapi_app.repositories.user_repository import UserRepository
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.repositories.agent_device_token_repository import AgentDeviceTokenRepository
from fastapi_app.dependencies.auth import get_current_agent, get_optional_agent, security
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.services.lock_unlock_service import LockUnlockService
from fastapi.security import HTTPAuthorizationCredentials
from fastapi_app.utils.auth import decode_access_token
from fastapi_app.models.user_token import UserToken

router = APIRouter(
    prefix="/v1/agents",
    tags=["Authentication"]
)

def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        agent_repo=AgentRepository(db),
        db=db
    )

@router.post("/login", response_model=LoginResponse, responses={
    200: {"description": "Successful login"},
    401: {"description": "Invalid email or password"},
    403: {"description": "Your account is pending approval or blocked"},
    404: {"description": "Agent profile not found"}
})
def login(request: LoginRequest, req: Request, auth_service: AuthService = Depends(get_auth_service)):
    return auth_service.login(request, req)

@router.get("/me", response_model=AgentMeResponse)
def get_me(current_agent: Agent = Depends(get_current_agent), db: Session = Depends(get_db)):
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == current_agent.id).first()
    lock_service = LockUnlockService(db)
    features_access = lock_service.get_feature_access_map(current_agent)

    agent_data = {
        "id": current_agent.id,
        "fullname": current_agent.fullname,
        "display_name": profile.display_name if profile and profile.display_name else current_agent.fullname,
        "email": current_agent.email,
        "mobile": current_agent.mobile,
        "status": current_agent.status,
        "plan_type": current_agent.plan_type,
        "profile_photo_url": profile.profile_photo_path if profile else None,
        "slug": profile.slug if profile and profile.slug else getattr(current_agent, 'agent_slug', str(current_agent.id)),
        "experience_range": current_agent.experience_range,
        "is_listed_in_directory": lock_service.is_feature_unlocked(current_agent, "agent_directory_visibility"),
        "features_access": features_access
    }
    
    return AgentMeResponse(
        success=True,
        data=agent_data
    )

@router.post("/logout", response_model=LogoutResponse)
def logout(
    current_agent: Agent = Depends(get_current_agent),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        jti = payload.get("jti")
        if jti:
            db.query(UserToken).filter(UserToken.jti == jti).update({"is_revoked": True})
            db.commit()
    except Exception:
        pass

    return LogoutResponse(
        success=True,
        message="Logged out successfully."
    )

def get_password_reset_service(db: Session = Depends(get_db)) -> PasswordResetService:
    return PasswordResetService(db)

@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request: ForgotPasswordRequest,
    req: Request,
    password_reset_service: PasswordResetService = Depends(get_password_reset_service)
):
    return await password_reset_service.send_reset_link(request, req)

@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    request: ResetPasswordRequest,
    req: Request,
    current_agent: Optional[Agent] = Depends(get_optional_agent),
    password_reset_service: PasswordResetService = Depends(get_password_reset_service)
):
    """
    Reset password using email reset token or authenticated session.
    """
    return password_reset_service.reset_password(request, req, current_agent=current_agent)

@router.post("/push-token", response_model=PushTokenResponse)
def register_push_token(
    payload: PushTokenRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Register FCM Push Notification Device Token for Android App.
    """
    if not payload.token or not payload.token.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Token cannot be empty")
    
    repo = AgentDeviceTokenRepository(db)
    repo.upsert_token(
        agent_id=current_agent.id,
        token=payload.token.strip(),
        platform=payload.platform or "android"
    )
    return PushTokenResponse(
        success=True,
        message="Push token registered successfully."
    )
