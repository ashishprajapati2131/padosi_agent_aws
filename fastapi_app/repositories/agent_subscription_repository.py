from typing import Optional
from sqlalchemy.orm import Session
from fastapi_app.models.agent_subscription import AgentSubscription

class AgentSubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent_id(self, agent_id: int) -> Optional[AgentSubscription]:
        return self.db.query(AgentSubscription).filter(AgentSubscription.agent_id == agent_id).first()

    def get_completed_by_plan(self, agent_id: int, plan_name: str) -> Optional[AgentSubscription]:
        return self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent_id,
            AgentSubscription.payment_status == 'completed',
            AgentSubscription.selected_plan == plan_name
        ).first()

    def update_or_create(self, agent_id: int, defaults: dict) -> AgentSubscription:
        subscription = self.get_by_agent_id(agent_id)
        if subscription:
            for key, value in defaults.items():
                setattr(subscription, key, value)
        else:
            subscription = AgentSubscription(agent_id=agent_id, **defaults)
            self.db.add(subscription)
        
        self.db.flush()
        return subscription
