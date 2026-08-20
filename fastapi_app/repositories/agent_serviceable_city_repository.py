from typing import List
from sqlalchemy.orm import Session
from fastapi_app.models.agent_serviceable_city import AgentServiceableCity
from fastapi_app.models.city import City

class AgentServiceableCityRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_cities_for_agent(self, agent_id: int) -> List[City]:
        """Return City objects for a given agent via the pivot table."""
        return (
            self.db.query(City)
            .join(AgentServiceableCity, AgentServiceableCity.city_id == City.id)
            .filter(AgentServiceableCity.agent_id == agent_id)
            .all()
        )

    def count_for_agent(self, agent_id: int) -> int:
        return self.db.query(AgentServiceableCity).filter(
            AgentServiceableCity.agent_id == agent_id
        ).count()
