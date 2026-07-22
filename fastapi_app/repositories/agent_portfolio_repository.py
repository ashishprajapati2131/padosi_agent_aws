from sqlalchemy.orm import Session
from app.models.agent_portfolio import AgentPortfolio

class AgentPortfolioRepository:
    def __init__(self, db: Session):
        self.db = db

    def count_by_agent(self, agent_id: int) -> int:
        return self.db.query(AgentPortfolio).filter(
            AgentPortfolio.agent_id == agent_id
        ).count()
