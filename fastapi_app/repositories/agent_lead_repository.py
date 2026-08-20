from typing import List
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi_app.models.agent_lead import AgentLead

class AgentLeadRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self, agent_id: int):
        return self.db.query(AgentLead).filter(AgentLead.agent_id == agent_id)

    def count_total(self, agent_id: int) -> int:
        return self._base_query(agent_id).count()

    def count_monthly(self, agent_id: int, start_of_month: datetime) -> int:
        return self._base_query(agent_id).filter(
            AgentLead.created_at >= start_of_month
        ).count()

    def count_by_status(self, agent_id: int, status: str) -> int:
        return self._base_query(agent_id).filter(
            AgentLead.lead_status == status
        ).count()

    def get_recent(self, agent_id: int, limit: int = 10) -> List[AgentLead]:
        return (
            self._base_query(agent_id)
            .order_by(AgentLead.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_leads_paginated(
        self,
        agent_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str = None,
        interaction_type: str = None,
        search: str = None
    ):
        query = self._base_query(agent_id)
        if status:
            query = query.filter(AgentLead.lead_status == status)
        if interaction_type:
            query = query.filter(AgentLead.interaction_type == interaction_type)
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (AgentLead.customer_name.like(search_pattern)) |
                (AgentLead.customer_email.like(search_pattern)) |
                (AgentLead.customer_mobile.like(search_pattern))
            )
        
        total = query.count()
        leads = (
            query.order_by(AgentLead.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return leads, total

    def update_lead_status(self, agent_id: int, lead_id: int, status: str) -> AgentLead:
        lead = self.db.query(AgentLead).filter(
            AgentLead.id == lead_id,
            AgentLead.agent_id == agent_id
        ).first()
        if lead:
            lead.lead_status = status
            self.db.commit()
            self.db.refresh(lead)
        return lead
