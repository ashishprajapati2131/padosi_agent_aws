from fastapi import Request, HTTPException, status
import logging
from app.config import settings

logger = logging.getLogger("security")

def verify_admin_ip(request: Request):
    # Only enforce if ADMIN_WHITELIST_IPS is configured
    if not settings.ADMIN_WHITELIST_IPS:
        return
        
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "127.0.0.1"
        
    # Always allow localhost
    if client_ip in ["127.0.0.1", "::1"]:
        return
        
    if client_ip not in settings.ADMIN_WHITELIST_IPS:
        logger.warning(
            f"Admin access blocked: unauthorized IP {client_ip} tried to access {request.url}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )
