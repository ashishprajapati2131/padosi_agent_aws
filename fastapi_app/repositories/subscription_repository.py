from sqlalchemy.orm import Session
from app.models.agent_subscription import AgentSubscription

class SubscriptionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_agent_id(self, agent_id: int) -> AgentSubscription:
        return self.db.query(AgentSubscription).filter(AgentSubscription.agent_id == agent_id).first()

    def get_by_order_id(self, order_id: str) -> AgentSubscription:
        return self.db.query(AgentSubscription).filter(AgentSubscription.razorpay_order_id == order_id).first()

    def create(self, subscription: AgentSubscription) -> AgentSubscription:
        self.db.add(subscription)
        self.db.flush()
        return subscription
