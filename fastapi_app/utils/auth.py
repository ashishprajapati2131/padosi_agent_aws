from datetime import datetime, timedelta
from typing import Optional, Union, Any
from uuid import uuid4
from jose import jwt, JWTError
from fastapi_app.config import settings

try:
    from password_hashing import check_password_hash, hash_password
except ImportError:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt", "django_pbkdf2_sha256"], deprecated="auto")

    def check_password_hash(plain_password, hashed_password):
        return _pwd_context.verify(plain_password, hashed_password)

    def hash_password(password):
        return _pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return check_password_hash(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return hash_password(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = to_encode.get("jti") or str(uuid4())
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": jti,
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = to_encode.get("jti") or str(uuid4())
    to_encode.update({
        "exp": expire,
        "iat": now,
        "nbf": now,
        "jti": jti,
        "type": "refresh",
    })
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

from sqlalchemy.orm import Session
def generate_and_register_token(db: Session, email: str, role: str, user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    from fastapi_app.models.user_token import UserToken
    jti = str(uuid4())
    token_version = 1
    now = datetime.utcnow()
    
    # For agent login, we want the token to never expire (100 years duration)
    # unless explicitly requested otherwise.
    if not expires_delta:
        expires_delta = timedelta(days=365 * 100)
        
    expire = now + expires_delta
        
    token = create_access_token(
        data={
            "sub": email,
            "role": role,
            "user_id": user_id,
            "token_version": token_version,
            "jti": jti
        },
        expires_delta=expires_delta
    )
    
    user_token = UserToken(
        jti=jti,
        user_id=user_id,
        token_version=token_version,
        is_revoked=False,
        expires_at=expire
    )
    db.add(user_token)
    db.flush()
    return token

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

def decode_access_token(token: str) -> dict:
    """Decodes and validates a JWT access token, raising JWTError if invalid or expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

def create_promo_validation_token(promo_code: str, promo_id: int) -> str:
    now = datetime.utcnow()
    expire = now + timedelta(minutes=20)
    to_encode = {
        "promo_code_id": promo_id,
        "promo_code": promo_code,
        "exp": expire,
        "iat": now,
        "jti": str(uuid4()),
        "purpose": "promo_validation"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_promo_validation_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("purpose") == "promo_validation":
            return payload
        return None
    except JWTError:
        return None

def generate_reset_token(app_key: Optional[str]) -> str:
    import base64
    import hmac
    import hashlib
    import secrets

    if not app_key:
        key_bytes = settings.SECRET_KEY.encode("utf-8")
    elif app_key.startswith("base64:"):
        try:
            key_bytes = base64.b64decode(app_key[7:])
        except Exception:
            key_bytes = app_key.encode("utf-8")
    else:
        key_bytes = app_key.encode("utf-8")

    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    random_str = "".join(secrets.choice(alphabet) for _ in range(40))

    return hmac.new(key_bytes, random_str.encode("utf-8"), hashlib.sha256).hexdigest()

