from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi_app.models.agent_profile_view import AgentProfileView

class AgentProfileViewRepository:
    def __init__(self, db: Session):
        self.db = db

    def sum_total_views(self, agent_id: int) -> int:
        result = self.db.query(
            func.sum(AgentProfileView.view_count)
        ).filter(AgentProfileView.agent_id == agent_id).scalar()
        return int(result or 0)

    def sum_monthly_views(self, agent_id: int, start_of_month: date) -> int:
        result = self.db.query(
            func.sum(AgentProfileView.view_count)
        ).filter(
            AgentProfileView.agent_id == agent_id,
            AgentProfileView.view_date >= start_of_month
        ).scalar()
        return int(result or 0)
