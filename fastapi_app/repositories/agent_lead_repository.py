from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi_app.models.agent_lead import AgentLead
from fastapi_app.models.agent_lead_preference import AgentLeadPreference

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

    def get_by_id(self, agent_id: int, lead_id: int) -> Optional[AgentLead]:
        return self.db.query(AgentLead).filter(
            AgentLead.id == lead_id,
            AgentLead.agent_id == agent_id
        ).first()

    def get_leads_paginated(
        self,
        agent_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str = None,
        interaction_type: str = None,
        search: str = None
    ) -> Tuple[List[AgentLead], int]:
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

    def update_lead_status(self, agent_id: int, lead_id: int, status: str) -> Optional[AgentLead]:
        lead = self.get_by_id(agent_id, lead_id)
        if lead:
            lead.lead_status = status
            self.db.commit()
            self.db.refresh(lead)
        return lead

    def capture_lead(self, agent_id: int, data: Dict[str, Any]) -> AgentLead:
        now = datetime.utcnow()
        lead = AgentLead(
            agent_id=agent_id,
            customer_name=data.get("customer_name"),
            customer_mobile=data.get("customer_mobile"),
            customer_email=data.get("customer_email"),
            customer_pincode=data.get("customer_pincode"),
            service_type=data.get("insurance_type") or data.get("service_type"),
            insurance_type=data.get("insurance_type"),
            insurance_company=data.get("insurance_company"),
            enquiry_requirements=data.get("enquiry_requirements"),
            interaction_type=data.get("interaction_type") or "manual",
            lead_status="new",
            source_page="agent_app_manual",
            created_at=now,
            updated_at=now
        )
        self.db.add(lead)
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def get_preferences(self, agent_id: int) -> Optional[AgentLeadPreference]:
        return self.db.query(AgentLeadPreference).filter(
            AgentLeadPreference.agent_id == agent_id
        ).first()

    def save_preferences(self, agent_id: int, data: Dict[str, Any]) -> AgentLeadPreference:
        pref = self.get_preferences(agent_id)
        if not pref:
            pref = AgentLeadPreference(agent_id=agent_id)
            self.db.add(pref)

        pref.leads_new_business = bool(data.get("leads_new_business", True))
        pref.leads_portfolio_analysis = bool(data.get("leads_portfolio_analysis", True))
        pref.portfolio_charging = data.get("portfolio_charging", "free")
        pref.portfolio_fee = float(data.get("portfolio_fee", 0.0))
        pref.leads_claims_support = bool(data.get("leads_claims_support", True))
        pref.claims_charging = data.get("claims_charging", "free")
        pref.claims_fee_amount = float(data.get("claims_fee_amount", 0.0))
        pref.claims_percent = float(data.get("claims_percent", 0.0))

        self.db.commit()
        self.db.refresh(pref)
        return pref
