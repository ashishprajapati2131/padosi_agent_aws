from typing import Optional
from sqlalchemy.orm import Session
from fastapi_app.models.referral_code import ReferralCode

class ReferralCodeRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent(self, agent_id: int) -> Optional[ReferralCode]:
        return self.db.query(ReferralCode).filter(
            ReferralCode.agent_id == agent_id
        ).first()
