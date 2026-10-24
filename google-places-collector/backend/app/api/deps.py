from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models import Search, User
from app.services.tokens import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    try:
        payload = decode_token(creds.credentials, "access")
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Your session has expired. Sign in again.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access is required.")
    return user


def client_ip(request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def owned_search(db: Session, user: User, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if search is None or (search.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="Search not found.")
    return search
