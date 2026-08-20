from typing import Optional
from sqlalchemy.orm import Session
from fastapi_app.models.agent_lead_preference import AgentLeadPreference

class AgentLeadPreferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent(self, agent_id: int) -> Optional[AgentLeadPreference]:
        return self.db.query(AgentLeadPreference).filter(
            AgentLeadPreference.agent_id == agent_id
        ).first()

    def exists_for_agent(self, agent_id: int) -> bool:
        return self.get_by_agent(agent_id) is not None
