from sqlalchemy.orm import Session
from app.models.promo_code import PromoCode

class PromoCodeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, code: str) -> PromoCode:
        return self.db.query(PromoCode).filter(PromoCode.code == code).first()
