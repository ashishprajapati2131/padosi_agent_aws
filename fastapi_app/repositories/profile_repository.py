from sqlalchemy.orm import Session
from app.models.agent_profile import AgentProfile

class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent_id(self, agent_id: int) -> AgentProfile:
        return self.db.query(AgentProfile).filter(AgentProfile.agent_id == agent_id).first()

    def create(self, profile: AgentProfile) -> AgentProfile:
        self.db.add(profile)
        self.db.flush()
        return profile
