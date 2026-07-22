from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from app.database import engine
from sqlalchemy import text
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def is_valid_admin_session(token: str) -> bool:
    if not token:
        return False
    now_utc = datetime.now(timezone.utc)
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                SELECT s.id 
                FROM user_sessions s
                JOIN user_session_data d ON s.id = d.session_id
                WHERE s.session_token = :token 
                  AND s.expires_at > :now_utc
                  AND d.data_key = 'admin_id'
                LIMIT 1
                """),
                {"token": token, "now_utc": now_utc}
            ).fetchone()
            return result is not None
    except Exception as e:
        logger.error(f"Error checking admin session in FastAPI middleware: {e}")
        return False

class AdminAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        session_token = request.cookies.get("session_token")
        
        if not is_valid_admin_session(session_token):
            accept_header = request.headers.get("accept", "")
            if "text/html" in accept_header or path in ["/docs", "/redoc", "/openapi.json", "/"]:
                return RedirectResponse(url="/admin/login/", status_code=307)
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "message": "Admin authentication required. Please log in to the admin panel."
                }
            )
            
        response = await call_next(request)
        return response
