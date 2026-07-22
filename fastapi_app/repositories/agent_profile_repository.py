from typing import Optional
from sqlalchemy.orm import Session
from app.models.agent_profile import AgentProfile

class AgentProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent_id(self, agent_id: int) -> Optional[AgentProfile]:
        return self.db.query(AgentProfile).filter(AgentProfile.agent_id == agent_id).first()

    def first_or_create(self, agent_id: int) -> AgentProfile:
        profile = self.get_by_agent_id(agent_id)
        if not profile:
            profile = AgentProfile(agent_id=agent_id)
            self.db.add(profile)
            self.db.flush()
        return profile
