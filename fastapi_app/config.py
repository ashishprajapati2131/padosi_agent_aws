import os
from typing import Optional, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator

# Clean up any trailing newlines or spaces from database environment variables (very common in Docker/Railway)
for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "MYSQLHOST", "MYSQLPORT", "MYSQLDATABASE", "MYSQLUSER", "MYSQLPASSWORD"]:
    if key in os.environ and os.environ[key]:
        os.environ[key] = os.environ[key].strip()

# Auto-detect Railway MySQL variables and map them
if "MYSQLHOST" in os.environ:
    os.environ["DB_HOST"] = os.getenv("MYSQLHOST", "").strip()
if "MYSQLPORT" in os.environ:
    os.environ["DB_PORT"] = os.getenv("MYSQLPORT", "").strip()
if "MYSQLDATABASE" in os.environ:
    os.environ["DB_NAME"] = os.getenv("MYSQLDATABASE", "").strip()
if "MYSQLUSER" in os.environ:
    os.environ["DB_USER"] = os.getenv("MYSQLUSER", "").strip()
if "MYSQLPASSWORD" in os.environ:
    os.environ["DB_PASSWORD"] = os.getenv("MYSQLPASSWORD", "").strip()

class Settings(BaseSettings):
    APP_KEY: Optional[str] = None
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "padosiagent"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    @model_validator(mode="before")
    @classmethod
    def strip_string_fields(cls, values):
        if isinstance(values, dict):
            for k, v in values.items():
                if isinstance(v, str):
                    values[k] = v.strip()
            for field in ["ALLOWED_CORS_ORIGINS", "ADMIN_WHITELIST_IPS"]:
                val = values.get(field)
                if isinstance(val, str) and val:
                    values[field] = [x.strip() for x in val.split(",") if x.strip()]
        return values

    # Auth & Security
    SECRET_KEY: str = "v2f6yt8&oq&%^=mh^1=w5y8v0-q3ks^s__$!2+&@5kcyn)wsd5"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Profile JWT Auth
    JWT_SECRET_KEY: str = "v2f6yt8&oq&%^=mh^1=w5y8v0-q3ks^s__$!2+&@5kcyn)wsd5"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    APP_URL: str = "http://localhost:8000"
    DEBUG: bool = False

    @model_validator(mode="after")
    def validate_production_app_url(self):
        is_debug = bool(self.DEBUG) or os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")
        is_localhost = any(h in (self.APP_URL or "").lower() for h in ("localhost", "127.0.0.1", "0.0.0.0"))
        if not is_debug and is_localhost:
            self.APP_URL = "https://padosiagent.com"
        return self

    # Razorpay Payments
    RAZORPAY_KEY: str = ""
    RAZORPAY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Firebase FCM
    FCM_PROJECT_ID: Optional[str] = "padosiagent-e74c8"
    FCM_SERVICE_ACCOUNT_JSON: Optional[str] = "storage/app/firebase-service-account.json"

    # Brevo Mail & SMTP configuration
    BREVO_API_KEY: str = ""
    BREVO_FROM_EMAIL: str = "noreply@padosiagent.com"
    BREVO_FROM_NAME: str = "PadosiAgent"
    BREVO_OTP_FALLBACK: bool = True

    MAIL_HOST: str = "smtp-relay.brevo.com"
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_ENCRYPTION: str = "tls"
    MAIL_FROM_ADDRESS: str = "noreply@padosiagent.com"
    MAIL_FROM_NAME: str = "PadosiAgent"

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Local Storage Fallback Path
    LOCAL_STORAGE_PATH: str = "media"

    # Security Config
    SECURITY_ALERT_EMAIL: str = "ashisprajapati2131@gmail.com"
    WAF_AUTO_BAN_ENABLED: bool = False  # Temporarily disabled for testing (do not lock agent after 3 attempts)
    ALLOWED_CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    ADMIN_WHITELIST_IPS: list[str] = []

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()


def get_base_url(request: Optional[Any] = None) -> str:
    """
    Get the absolute base URL for building links and asset paths.
    Prioritizes incoming request headers (x-forwarded-proto, host) so that
    production reverse proxies (Passenger WSGI, Nginx, ALB) correctly reflect the public domain.
    Falls back to settings.APP_URL or https://padosiagent.com in production.
    """
    if request is not None and hasattr(request, "headers"):
        proto = request.headers.get("x-forwarded-proto")
        if not proto:
            proto = getattr(getattr(request, "url", None), "scheme", "") or "https"
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if not host and hasattr(request, "url"):
            host = getattr(request.url, "netloc", "")

        if host:
            is_localhost = any(lh in host.lower() for lh in ("localhost", "127.0.0.1", "testserver"))
            if not is_localhost:
                return f"{proto}://{host}".rstrip('/')

            # Host is localhost: check if settings.APP_URL has a production domain
            if settings.APP_URL and not any(lh in settings.APP_URL.lower() for lh in ("localhost", "127.0.0.1")):
                return settings.APP_URL.rstrip('/')

            # If both request and settings are localhost, check if in production
            is_debug = bool(settings.DEBUG) or os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")
            if not is_debug:
                return "https://padosiagent.com"
            return f"{proto}://{host}".rstrip('/')

    # No request provided
    app_url = (settings.APP_URL or "").rstrip('/')
    is_localhost = any(lh in app_url.lower() for lh in ("localhost", "127.0.0.1"))
    is_debug = bool(settings.DEBUG) or os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")
    if is_localhost and not is_debug:
        return "https://padosiagent.com"
    return app_url or "https://padosiagent.com"



