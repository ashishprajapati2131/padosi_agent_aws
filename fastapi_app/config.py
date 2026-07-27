import os
from typing import Optional
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
    DB_PASSWORD: str = "12PassworD!@"

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
    LOCAL_STORAGE_PATH: str = "storage"

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


