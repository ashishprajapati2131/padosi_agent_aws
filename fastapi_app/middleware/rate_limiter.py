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
        
    async def dispatch(self, request: Request, call_next):
        # Allow static files and health check routes without limits
        path = request.url.path
        if path.startswith("/static") or path == "/":
            return await call_next(request)
            
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "127.0.0.1"
            
        # Bypass localhost checks
        if ip in ["127.0.0.1", "::1", "testclient"]:
            return await call_next(request)
            
        current_time = time.time()
        
        # Keep only requests within the sliding window
        valid_timestamps = [
            t for t in self.client_records.get(ip, []) 
            if current_time - t < self.window_seconds
        ]
        if valid_timestamps:
            self.client_records[ip] = valid_timestamps
        elif ip in self.client_records:
            del self.client_records[ip]
        
        # Periodic memory cleanup if dict grows large
        if len(self.client_records) > 2000:
            stale_ips = [
                k for k, timestamps in self.client_records.items()
                if not timestamps or (current_time - timestamps[-1] >= self.window_seconds)
            ]
            for k in stale_ips:
                self.client_records.pop(k, None)
        
        # Enforce rate limits (e.g. login or checkouts can have lower limits in the future,
        # but here we apply a general limit per IP)
        limit = self.requests_limit
        if any(marker in path for marker in SENSITIVE_PATH_MARKERS):
            limit = 15  # Tighter limit on sensitive endpoints
            
        if len(self.client_records.get(ip, [])) >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": "Too Many Requests", "message": "Rate limit exceeded. Please try again later."}
            )
            
        self.client_records[ip].append(current_time)
        return await call_next(request)
