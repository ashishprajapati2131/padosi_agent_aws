from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
import time
from collections import defaultdict

# Substrings of the real router paths. The earlier "/auth/login" marker never
# matched, so credential and payment endpoints ran on the generic 100/min limit.
SENSITIVE_PATH_MARKERS = (
    "/agents/login",
    "/agents/forgot-password",
    "/agents/reset-password",
    "/payment-order",
    "/payment/success",
)

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_limit: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        self.client_records = defaultdict(list)

    @staticmethod
    def get_client_ip(request: Request) -> str:
        from fastapi_app.utils.client_ip import get_client_ip
        return get_client_ip(request)
        
    async def dispatch(self, request: Request, call_next):
        # Allow static files and health check routes without limits
        path = request.url.path
        if path.startswith("/static") or path == "/":
            return await call_next(request)
            
        client_host = request.client.host if request.client else "127.0.0.1"
        ip = self.get_client_ip(request)
            
        # Bypass localhost checks only if direct connection is genuinely local
        if client_host in ["127.0.0.1", "::1", "testclient", "localhost", "testserver"] and ip in ["127.0.0.1", "::1", "testclient", "localhost", "testserver"]:
            return await call_next(request)
            
        is_sensitive = any(marker in path for marker in SENSITIVE_PATH_MARKERS)
        bucket = "sensitive" if is_sensitive else "general"
        bucket_key = (ip, bucket)
        limit = 15 if is_sensitive else self.requests_limit
        
        current_time = time.time()
        
        # Keep only requests within the sliding window for this specific bucket
        valid_timestamps = [
            t for t in self.client_records.get(bucket_key, []) 
            if current_time - t < self.window_seconds
        ]
        if valid_timestamps:
            self.client_records[bucket_key] = valid_timestamps
        elif bucket_key in self.client_records:
            del self.client_records[bucket_key]
        
        # Periodic memory cleanup if dict grows large
        if len(self.client_records) > 2000:
            stale_keys = [
                k for k, timestamps in self.client_records.items()
                if not timestamps or (current_time - timestamps[-1] >= self.window_seconds)
            ]
            for k in stale_keys:
                self.client_records.pop(k, None)
        
        if len(self.client_records.get(bucket_key, [])) >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "message": "Rate limit exceeded. Please try again later."}
            )
            
        self.client_records[bucket_key].append(current_time)
        return await call_next(request)
