from sqlalchemy.orm import Session
from sqlalchemy import text, func
from fastapi_app.models.password_reset_token import PasswordResetToken
from datetime import datetime

class PasswordResetTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def delete_by_email(self, email: str) -> None:
        self.db.query(PasswordResetToken).filter(PasswordResetToken.email == email).delete()
        self.db.flush()

    def create(self, email: str, hashed_token: str) -> PasswordResetToken:
        # Delete existing first to ensure uniqueness (since email is primary key)
        self.delete_by_email(email)
        
        token_record = PasswordResetToken(
            email=email,
            token=hashed_token,
            created_at=datetime.utcnow()
        )
        self.db.add(token_record)
        self.db.flush()
        return token_record

    def get_valid_token_record(self, email: str, expire_minutes: int = 60) -> PasswordResetToken:
        # Use database-level timezone-safe filter:
        # created_at must be >= (current database UTC time - expire_minutes)
        time_limit = func.utc_timestamp() - text(f"INTERVAL {expire_minutes} MINUTE")
        return self.db.query(PasswordResetToken).filter(
            PasswordResetToken.email == email,
            PasswordResetToken.created_at >= time_limit
        ).first()
