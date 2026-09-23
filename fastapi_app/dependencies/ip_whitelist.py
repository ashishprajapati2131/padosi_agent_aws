from fastapi import Request, HTTPException, status
import logging
from fastapi_app.config import settings

logger = logging.getLogger("security")

def verify_admin_ip(request: Request):
    # Only enforce if ADMIN_WHITELIST_IPS is configured
    if not settings.ADMIN_WHITELIST_IPS:
        return
        
    # X-Forwarded-For is only trusted from the local proxy; before, sending
    # "X-Forwarded-For: 127.0.0.1" bypassed the whitelist via the localhost rule.
    from fastapi_app.utils.client_ip import get_client_ip
    client_ip = get_client_ip(request)

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
