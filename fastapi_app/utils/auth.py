from datetime import datetime, timedelta, timezone
from typing import Optional
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

# Sentinel stored on UserToken.expires_at for non-expiring agent session JWTs.
# JWT itself omits `exp`; logout revokes via jti. MySQL DATETIME max year is 9999.
SESSION_TOKEN_SENTINEL_EXPIRY = datetime(9999, 12, 31, 23, 59, 59)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
    *,
    never_expire: bool = False,
) -> str:
    """Build a JWT. Agent login sessions use never_expire=True (no `exp` claim)."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    jti = to_encode.get("jti") or str(uuid4())
    to_encode.update({
        "iat": now,
        "nbf": now,
        "jti": jti,
    })
    if never_expire:
        # No `exp` → token stays valid until logout revokes its jti.
        to_encode.pop("exp", None)
    else:
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode["exp"] = expire
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

from sqlalchemy.orm import Session
def generate_and_register_token(
    db: Session,
    email: str,
    role: str,
    user_id: int,
    expires_delta: Optional[timedelta] = None,
    *,
    never_expire: bool = True,
) -> str:
    """Issue a registered agent JWT.

    Default never_expire=True: token does not time out; only logout (jti revoke)
    or account status checks invalidate it. Pass expires_delta / never_expire=False
    only when a timed token is explicitly required.
    """
    from fastapi_app.models.user_token import UserToken
    jti = str(uuid4())
    token_version = 1
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        never_expire = False

    if never_expire:
        expire = SESSION_TOKEN_SENTINEL_EXPIRY
    else:
        if not expires_delta:
            expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = now + expires_delta

    token = create_access_token(
        data={
            "sub": email,
            "role": role,
            "user_id": user_id,
            "token_version": token_version,
            "jti": jti
        },
        expires_delta=expires_delta,
        never_expire=never_expire,
    )

    user_token = UserToken(
        jti=jti,
        user_id=user_id,
        token_version=token_version,
        is_revoked=False,
        expires_at=expire.replace(tzinfo=None) if getattr(expire, "tzinfo", None) else expire,
    )
    db.add(user_token)
    db.flush()
    return token

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": True},
        )
        return payload
    except JWTError:
        return None

def decode_access_token(token: str) -> dict:
    """Decodes and validates a JWT access token, raising JWTError if invalid or expired.

    Tokens without an `exp` claim (non-expiring agent sessions) are accepted;
    jose only enforces exp when the claim is present.
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_exp": True},
    )

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

