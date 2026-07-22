from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings
import urllib.parse

print("=" * 50)
print("DB_HOST:", settings.DB_HOST)
print("DB_PORT:", settings.DB_PORT)
print("DB_NAME:", settings.DB_NAME)
print("DB_USER:", settings.DB_USER)
print(f"PASSWORD_LENGTH: {len(settings.DB_PASSWORD) if settings.DB_PASSWORD else 0}")
print("=" * 50)

encoded_password = urllib.parse.quote_plus(settings.DB_PASSWORD) if settings.DB_PASSWORD else ""

DATABASE_URL = (
    f"mysql+pymysql://{settings.DB_USER}:"
    f"{encoded_password}@"
    f"{settings.DB_HOST}:"
    f"{settings.DB_PORT}/"
    f"{settings.DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=50,
    max_overflow=20,
    pool_recycle=3600,
    pool_timeout=30,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print("✓ Successfully connected to MySQL")
except Exception as e:
    print(f"Database connection failed: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()