from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.utils.auth import decode_access_token
from fastapi_app.repositories.user_repository import UserRepository
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.models.agent import Agent
from fastapi_app.models.user import User
from jose.exceptions import ExpiredSignatureError, JWTError

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub")
        role: str = payload.get("role")
        jti: str = payload.get("jti")
        token_user_id = payload.get("user_id")
        if email is None or role != "agent":
            raise credentials_exception

        # Every token we issue carries a registered jti (generate_and_register_token).
        # A token without one was never issued by us, so it must not skip the
        # revocation registry.
        if not jti:
            raise credentials_exception
        from fastapi_app.models.user_token import UserToken
        token_record = db.query(UserToken).filter(UserToken.jti == jti).first()
        if not token_record or token_record.is_revoked:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is invalid or has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception
        
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(email)
    # The `sub` claim is the email captured at login. An agent who changes their
    # email keeps a valid, unrevoked token, so fall back to the user id claim
    # instead of forcing a re-login they cannot complete.
    if user is None and token_user_id is not None:
        user = db.query(User).filter(User.id == token_user_id).first()
    if user is None:
        raise credentials_exception
        
    if user.status in ("suspended", "inactive"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User account is {user.status}"
        )
        
    return user

# Mirrors AuthService.BLOCKED_AGENT_STATUSES and Django's agent_login guard.
BLOCKED_AGENT_STATUSES = ("suspended", "blacklisted", "rejected", "deleted")

# Renewal and sign-out stay open to an expired agent, as Django's payment gate leaves
# /chooseplan/ and logout open (invariant 12).
_EXPIRY_EXEMPT_ROUTES = ("/v1/agents/me", "/v1/agents/logout")
_EXPIRY_EXEMPT_ROUTE_PREFIXES = ("/v1/agents/plans", "/v1/agents/plan-upgrade/")


def get_current_agent(
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Agent:
    agent_repo = AgentRepository(db)
    agent = agent_repo.get_by_email(current_user.email)
    if not agent and current_user.id:
        # Cross-verify email to protect against IDOR when users.id diverges from auth_user.id
        candidate = db.query(Agent).filter(Agent.user_id == current_user.id).first()
        if candidate and candidate.email.lower() == current_user.email.lower():
            agent = candidate
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found."
        )

    from apps.agents.services.account_auth import (
        ACCOUNT_RESTRICTED_MESSAGE,
        agent_account_is_active,
    )
    if not agent_account_is_active(agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ACCOUNT_RESTRICTED_MESSAGE,
        )

    if agent.status in BLOCKED_AGENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your account is currently {agent.status}."
        )

    # request is None only for get_optional_agent (plans list, reset password): left open.
    route_path = getattr((request.scope.get("route") if request is not None else None), "path", "") or ""
    if (
        request is not None
        and route_path not in _EXPIRY_EXEMPT_ROUTES
        and not route_path.startswith(_EXPIRY_EXEMPT_ROUTE_PREFIXES)
    ):
        from fastapi_app.services.lock_unlock_service import agent_subscription_expired
        if agent_subscription_expired(db, agent):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your subscription has expired. Please renew your plan to continue.",
            )

    return agent


def get_optional_agent(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: Session = Depends(get_db)
) -> Optional[Agent]:
    """Optional agent dependency for endpoints that work both authenticated and unauthenticated."""
    if not credentials:
        return None
    try:
        current_user = get_current_user(credentials=credentials, db=db)
        return get_current_agent(current_user=current_user, db=db)
    except Exception:
        return None


