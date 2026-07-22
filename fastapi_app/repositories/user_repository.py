from sqlalchemy.orm import Session
from app.models.user import User

class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User:
        from sqlalchemy import func
        return self.db.query(User).filter(func.lower(User.email) == func.lower(email)).first()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user
