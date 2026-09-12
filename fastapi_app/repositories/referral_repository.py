from typing import Optional
from sqlalchemy.orm import Session
from fastapi_app.models.referral_code import ReferralCode
from fastapi_app.models.referral_usage import ReferralUsage
import random
import string

class ReferralRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, code: str) -> Optional[ReferralCode]:
        return self.db.query(ReferralCode).filter(ReferralCode.code == code).first()

    def get_by_agent_id(self, agent_id: int) -> Optional[ReferralCode]:
        return self.db.query(ReferralCode).filter(ReferralCode.agent_id == agent_id).first()

    def get_by_agent(self, agent_id: int) -> Optional[ReferralCode]:
        return self.get_by_agent_id(agent_id)

    def create_code(self, referral_code: ReferralCode) -> ReferralCode:
        self.db.add(referral_code)
        self.db.flush()
        return referral_code

    def create_usage(self, usage: ReferralUsage) -> ReferralUsage:
        self.db.add(usage)
        self.db.flush()
        return usage

    def get_usage(self, referral_code_id: int, referred_agent_id: int) -> Optional[ReferralUsage]:
        return self.db.query(ReferralUsage).filter(
            ReferralUsage.referral_code_id == referral_code_id,
            ReferralUsage.referred_agent_id == referred_agent_id
        ).first()

    def count_conversions(self, referral_code_id: int) -> int:
        return self.db.query(ReferralUsage).filter(
            ReferralUsage.referral_code_id == referral_code_id,
            ReferralUsage.status == "converted"
        ).count()

    def generate_unique_code(self) -> str:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            if not self.db.query(ReferralCode).filter(ReferralCode.code == code).first():
                return code
