from sqlalchemy.orm import Session
from fastapi_app.repositories.user_repository import UserRepository
from fastapi_app.repositories.password_reset_token_repository import PasswordResetTokenRepository
from fastapi_app.services.email_service import EmailService
from fastapi_app.config import settings
from fastapi_app.utils.auth import generate_reset_token, get_password_hash, verify_password, decode_access_token
from fastapi_app.schemas.auth import ForgotPasswordRequest, ResetPasswordRequest
from fastapi import Request
from fastapi.responses import JSONResponse
from typing import Optional
import secrets
import urllib.parse

class PasswordResetService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.token_repo = PasswordResetTokenRepository(db)

    async def send_reset_link(self, request: ForgotPasswordRequest, req: Optional[Request] = None) -> JSONResponse:
        # 1. Fetch User by email
        user = self.user_repo.get_by_email(request.email)
        
        # 2. If user does not exist, return error indicating email is not registered
        if not user:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": f"{request.email} is not registered."
                }
            )

        # 3. Validation matching Laravel: Admin accounts cannot use this reset flow
        if user.role == "admin":
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Admin accounts cannot use this reset flow."
                }
            )

        # 4. Validation matching Laravel: Login page matching validation
        if user.role != request.login_type:
            other = "Distributor" if request.login_type == "agent" else "Agent"
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": f"This email belongs to a {other} account. Please use the {other} login page."
                }
            )

        try:
            # 5. Generate token (raw token is sent to the user, hashed token goes to database)
            raw_token = generate_reset_token(settings.APP_KEY)
            hashed_token = get_password_hash(raw_token)
            
            # 6. Save in database (deletes previous tokens for this email)
            self.token_repo.create(user.email, hashed_token)
            
            # 7. Formulate reset URL
            # URL structure: {APP_URL}{mount}/reset-password/{raw_token}?email={email}&type={login_type}
            # The service is mounted under /api inside the Django ASGI app, so
            # the link has to carry that prefix or it resolves to Django and 404s.
            base_url = settings.APP_URL
            mount_prefix = ""
            if req:
                proto = req.headers.get("x-forwarded-proto", req.url.scheme)
                host = req.headers.get("x-forwarded-host", req.headers.get("host", req.url.netloc))
                base_url = f"{proto}://{host}"
                mount_prefix = req.scope.get("root_path", "") or ""

            reset_url = (
                f"{base_url}{mount_prefix}/reset-password/{raw_token}"
                f"?email={urllib.parse.quote(user.email)}"
                f"&type={request.login_type}"
            )
            
            # 8. Send branded email
            role_name = "Distributor" if request.login_type == "distributor" else "Agent"
            
            success = await EmailService.send_password_reset_email(
                to_email=user.email,
                to_name=user.fullname,
                reset_url=reset_url,
                expiry_minutes=60,
                role_name=role_name
            )
            
            if not success:
                raise Exception("Email dispatch failed.")
                
            self.db.commit()
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": f"We have successfully sent the password reset link to {request.email}."
                }
            )
        except Exception as e:
            self.db.rollback()
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Unable to send reset email. Please try again later."
                }
            )

    def reset_password(self, request: ResetPasswordRequest, req: Optional[Request] = None) -> JSONResponse:
        # Check if they are authenticated via Bearer token in the request header OR via JWT token in request body
        authenticated_user = None
        jwt_token = None
        
        if req:
            auth_header = req.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                jwt_token = auth_header.split(" ")[1]
                
        if not jwt_token and request.token:
            if request.token.startswith("ey") and request.token.count(".") == 2:
                jwt_token = request.token

        if jwt_token:
            try:
                payload = decode_access_token(jwt_token)
                email = payload.get("sub")
                jti = payload.get("jti")
                if email and jti:
                    # Validate token is not revoked in DB
                    from fastapi_app.models.user_token import UserToken
                    token_record = self.db.query(UserToken).filter(UserToken.jti == jti).first()
                    if token_record and not token_record.is_revoked:
                        user = self.user_repo.get_by_email(email)
                        if user and user.status == "active":
                            authenticated_user = user
            except Exception:
                pass

        # If authenticated, bypass email reset token checks
        if authenticated_user:
            user = authenticated_user
        else:
            # 1. Fetch User by email
            user = self.user_repo.get_by_email(request.email)
            if not user:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "This email is not registered."
                    }
                )

            # 2. Fetch valid token record
            token_record = self.token_repo.get_valid_token_record(user.email)
            if not token_record:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "This password reset token is invalid or has expired."
                    }
                )

            # 3. Check token matches (bcrypt hash verify)
            if not verify_password(request.token, token_record.token):
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "message": "This password reset token is invalid."
                    }
                )

        try:
            # 4. Update password and generate a remember token
            user.password = get_password_hash(request.password)
            user.remember_token = secrets.token_hex(30) # 60 characters
            
            # 5. Delete the reset token from database
            if not authenticated_user:
                self.token_repo.delete_by_email(user.email)
            
            self.db.commit()
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Your password has been reset successfully! Please log in."
                }
            )
        except Exception as e:
            self.db.rollback()
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "An error occurred while resetting your password. Please try again."
                }
            )
