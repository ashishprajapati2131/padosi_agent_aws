from fastapi import APIRouter, Depends, status, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.schemas.auth import LoginRequest, LoginResponse, AgentMeResponse, LogoutResponse, ForgotPasswordRequest, ForgotPasswordResponse, ResetPasswordRequest, ResetPasswordResponse
from fastapi_app.services.auth_service import AuthService
from fastapi_app.services.password_reset_service import PasswordResetService
from fastapi_app.repositories.user_repository import UserRepository
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.dependencies.auth import get_current_agent, security
from fastapi_app.models.agent import Agent
from fastapi.security import HTTPAuthorizationCredentials
from fastapi_app.utils.auth import decode_access_token
from fastapi_app.models.user_token import UserToken

router = APIRouter(
    prefix="/api/v1/agents",
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
    403: {"description": "Your account is pending approval"},
    404: {"description": "Agent profile not found"}
})
def login(request: LoginRequest, req: Request, auth_service: AuthService = Depends(get_auth_service)):
    return auth_service.login(request, req)

@router.get("/me", response_model=AgentMeResponse)
def get_me(current_agent: Agent = Depends(get_current_agent)):
    agent_data = {
        "id": current_agent.id,
        "fullname": current_agent.fullname,
        "email": current_agent.email,
        "mobile": current_agent.mobile,
        "status": current_agent.status
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
        # Ignore errors during decoding to allow safe logouts anyway
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
    password_reset_service: PasswordResetService = Depends(get_password_reset_service)
):
    return password_reset_service.reset_password(request, req)
