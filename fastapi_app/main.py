from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.threat_monitor import ThreatMonitorMiddleware
from app.middleware.rate_limiter import RateLimitMiddleware
import os

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))
import logging
import time
from app.config import settings
from sqlalchemy.exc import OperationalError

from app.routers import (
    registration, promo_code, email,
    auth, dashboard, profile, public_profile,
    pincode, leads
)

from app.database import Base, engine
import app.models

logger = logging.getLogger(__name__)

# Resilient database connection and migration check on startup
for i in range(5):
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✓ Database tables verified/created successfully.")
        break
    except OperationalError as oe:
        if i == 4:
            logger.critical("Database connection failed after 5 retries. Exiting.")
            raise oe
        logger.warning(f"Database not ready yet (retry {i+1}/5): {oe}. Waiting 2 seconds...")
        time.sleep(2)

app = FastAPI(
    title="PadosiAgent FastAPI Service",
    description="Backend API for PadosiAgent Mobile App",
    version="1.0.0"
)

# Register Security & Request Processing Middlewares (LIFO Order)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, requests_limit=100, window_seconds=60)
app.add_middleware(ThreatMonitorMiddleware)

# Include all consolidated routers
app.include_router(registration.router)
app.include_router(promo_code.router)
app.include_router(email.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(profile.router)
app.include_router(public_profile.router)
app.include_router(pincode.router)
app.include_router(leads.router)

# Mount local storage directory for static access
os.makedirs(settings.LOCAL_STORAGE_PATH, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.LOCAL_STORAGE_PATH), name="static")

@app.get("/reset-password/{token}", response_class=HTMLResponse)
def get_reset_password_page(request: Request, token: str, email: str, type: str = "agent"):
    return templates.TemplateResponse(
        request=request,
        name="reset_password.html",
        context={
            "token": token,
            "email": email,
            "login_type": type,
            "app_url": settings.APP_URL
        }
    )


def clean_error(err):
    if isinstance(err, dict):
        cleaned = {}
        for k, v in err.items():
            if k == 'ctx' and isinstance(v, dict):
                cleaned_ctx = {}
                for ctx_k, ctx_v in v.items():
                    if ctx_k == 'error' and isinstance(ctx_v, Exception):
                        cleaned_ctx[ctx_k] = str(ctx_v)
                    else:
                        cleaned_ctx[ctx_k] = clean_error(ctx_v)
                cleaned[k] = cleaned_ctx
            else:
                cleaned[k] = clean_error(v)
        return cleaned
    elif isinstance(err, list):
        return [clean_error(item) for item in err]
    elif isinstance(err, Exception):
        return str(err)
    else:
        return err

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"422 Validation Error on {request.method} {request.url}")
    logger.error(f"Validation details: {exc.errors()}")
    
    errors_dict = {}
    for error in exc.errors():
        loc = error.get("loc", [])
        field = str(loc[-1]) if loc else "non_field_errors"
        msg = error.get("msg", "Validation error")
        
        # Clean up Pydantic V2 prefixes
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        elif msg.startswith("Assertion failed, "):
            msg = msg[len("Assertion failed, "):]
            
        if field not in errors_dict:
            errors_dict[field] = []
        errors_dict[field].append(msg)
        
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed",
            "errors": errors_dict
        },
    )

@app.get("/")
def health_check():
    return {"status": "ok", "service": "PadosiAgent FastAPI"}

@app.get("/get-ip")
def get_ip(request: Request):
    return {"ip": request.client.host}