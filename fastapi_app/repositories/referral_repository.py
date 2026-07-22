from sqlalchemy.orm import Session
from app.models.referral_code import ReferralCode
from app.models.referral_usage import ReferralUsage
import random
import string

class ReferralRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_code(self, code: str) -> ReferralCode:
        return self.db.query(ReferralCode).filter(ReferralCode.code == code).first()

    def get_by_agent_id(self, agent_id: int) -> ReferralCode:
        return self.db.query(ReferralCode).filter(ReferralCode.agent_id == agent_id).first()

    def create_code(self, referral_code: ReferralCode) -> ReferralCode:
        self.db.add(referral_code)
        self.db.flush()
        return referral_code

    def create_usage(self, usage: ReferralUsage) -> ReferralUsage:
        self.db.add(usage)
        self.db.flush()
        return usage

    def get_usage(self, referral_code_id: int, referred_agent_id: int) -> ReferralUsage:
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
