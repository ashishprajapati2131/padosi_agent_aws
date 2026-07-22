from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.schemas.auth import LoginRequest, LoginResponse
from app.repositories.user_repository import UserRepository
from app.repositories.agent_repository import AgentRepository
from app.utils.auth import verify_password, generate_and_register_token
from app.config import settings
from datetime import datetime
import time

# Simple in-memory throttle store: {ip: {"attempts": int, "expires_at": float}}
login_attempts_store = {}

def check_login_throttle(ip: str) -> bool:
    record = login_attempts_store.get(ip)
    if record:
        if time.time() > record["expires_at"]:
            login_attempts_store.pop(ip, None)
            return True
        if record["attempts"] >= 6:
            return False
    return True

def record_login_attempt(ip: str):
    record = login_attempts_store.get(ip)
    now = time.time()
    if not record or now > record["expires_at"]:
        login_attempts_store[ip] = {"attempts": 1, "expires_at": now + 60}
    else:
        login_attempts_store[ip]["attempts"] += 1

def clear_login_throttle(ip: str):
    login_attempts_store.pop(ip, None)

class AuthService:
    def __init__(self, user_repo: UserRepository, agent_repo: AgentRepository, db: Session):
        self.user_repo = user_repo
        self.agent_repo = agent_repo
        self.db = db

    def login(self, request: LoginRequest, req: Request) -> JSONResponse:
        # Extract client IP
        forwarded = req.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = req.client.host if req.client else "127.0.0.1"

        # Rate Limit check
        if not check_login_throttle(ip):
            return JSONResponse(
                status_code=429,
                content={"success": False, "message": "Too many login attempts. Please try again after 1 minute."}
            )

        # Check for empty credentials
        if not request.email or not request.password:
            record_login_attempt(ip)
            return JSONResponse(
                status_code=400,
                content={"success": False, "message": "Please enter both email and password."}
            )

        # 1. Fetch User by email
        user = self.user_repo.get_by_email(request.email)
        if not user:
            record_login_attempt(ip)
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Please Enter Valid Login Details"}
            )

        # 2. Verify password
        if not verify_password(request.password, user.password):
            record_login_attempt(ip)
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Please Enter Valid Login Details"}
            )

        # 3. Check role
        if user.role != 'agent':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=401,
                content={"success": False, "message": "Please use the correct login page for your account type."}
            )

        # 4. Check linked agent exists
        agent = self.agent_repo.get_by_email(user.email)
        if not agent:
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Agent profile not found."}
            )

        # 5. Check account status matching Django/Laravel
        if user.status == 'suspended':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Your account has been suspended."}
            )
            
        if user.status == 'inactive':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Your account is currently inactive."}
            )

        # Check Agent status specifically matching Django
        if agent.status == 'incomplete':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Please complete plan selection and payment to activate your account."}
            )
        elif agent.status == 'pending':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Your payment has been verified. Your account is pending admin approval."}
            )
        elif agent.status != 'active':
            record_login_attempt(ip)
            return JSONResponse(
                status_code=200,
                content={"success": False, "message": "Your account is not active."}
            )

        # Clear login throttle on successful auth
        clear_login_throttle(ip)

        # Update last login time
        user.last_login_at = datetime.utcnow()

        # 6. Generate and register unique JWT token in DB transactionally
        try:
            access_token = generate_and_register_token(
                db=self.db,
                email=user.email,
                role=user.role,
                user_id=user.id
            )
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            return JSONResponse(
                status_code=500,
                content={"success": False, "message": "Authentication failed due to database transaction error."}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Login successful.",
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 100 * 365 * 24 * 3600  # 100 years in seconds
            }
        )
