import os
import urllib.parse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from fastapi_app.config import settings

encoded_password = urllib.parse.quote_plus(settings.DB_PASSWORD) if settings.DB_PASSWORD else ""

DATABASE_URL = (
    f"mysql+pymysql://{settings.DB_USER}:"
    f"{encoded_password}@"
    f"{settings.DB_HOST}:"
    f"{settings.DB_PORT}/"
    f"{settings.DB_NAME}"
)

# Passenger/cPanel typically runs several workers against a shared MySQL
# connection limit. Keep the pool small and configurable.
_pool_size = int(os.environ.get("DB_POOL_SIZE", "5"))
_max_overflow = int(os.environ.get("DB_MAX_OVERFLOW", "10"))
_pool_recycle = int(os.environ.get("DB_POOL_RECYCLE", "1800"))

engine = create_engine(
    DATABASE_URL,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_recycle=_pool_recycle,
    pool_timeout=30,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
