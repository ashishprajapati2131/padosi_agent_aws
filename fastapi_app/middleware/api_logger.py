import json
import time
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.database import SessionLocal
from app.models.api_log import ApiLog
import asyncio
import logging

logger = logging.getLogger(__name__)

async def log_request_to_db(service: str, url: str, method: str, payload_str: str, response_code: int, ip_address: str):
    """Background task to save the API log to DB."""
    db = SessionLocal()
    try:
        # Convert payload string to dict if possible
        payload_data = None
        if payload_str:
            try:
                payload_data = json.loads(payload_str)
                # Redact sensitive fields
                if isinstance(payload_data, dict):
                    for key in ['password', 'password_confirmation', 'token']:
                        if key in payload_data:
                            payload_data[key] = '***REDACTED***'
            except json.JSONDecodeError:
                payload_data = {"raw_payload": payload_str[:1000]} # truncate

        log_entry = ApiLog(
            service=service,
            request_url=url,
            method=method,
            payload=payload_data,
            response=None, # Not logging full response body to save space
            response_code=response_code,
            ip_address=ip_address
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to save API log: {e}")
    finally:
        db.close()


class APILoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # We only want to log requests that go to our API endpoints
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # For GET requests or requests without a body, this is simple.
        # For POST/PUT, reading the body in BaseHTTPMiddleware can consume the stream.
        # A common trick is to stream the body into a buffer, but this can be slow.
        # We will only capture query params and avoid the body unless it's a specific webhook.
        
        url_path = request.url.path
        if request.url.query:
            url_path += f"?{request.url.query}"
            
        client_host = request.client.host if request.client else None

        # Webhook endpoints log their own rows with the full payload (body
        # cannot be read here without consuming the request stream).
        if "/payment/webhook" in url_path:
            return await call_next(request)

        # Determine service
        service = "fastapi"
        if "/razorpay/" in url_path or url_path.endswith("/payment/webhook"):
            service = "razorpay"
        elif "/fcm/" in url_path:
            service = "fcm"
            
        # Proceed with request
        start_time = time.time()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as e:
            status_code = 500
            raise e
        finally:
            # We don't block the response to save logs.
            # Using asyncio.create_task to run it in the background.
            asyncio.create_task(log_request_to_db(
                service=service,
                url=url_path,
                method=request.method,
                payload_str=None, # Skipping body to avoid stream issues
                response_code=status_code,
                ip_address=client_host
            ))

        return response
