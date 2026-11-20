from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi_app.models.agent_review import AgentReview


class AgentReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def _base_query(self, agent_id: int):
        return self.db.query(AgentReview).filter(AgentReview.agent_id == agent_id)

    def count_approved(self, agent_id: int) -> int:
        return (
            self._base_query(agent_id)
            .filter(AgentReview.is_approved.is_(True))
            .count()
        )

    def count_pending(self, agent_id: int) -> int:
        return (
            self._base_query(agent_id)
            .filter(AgentReview.is_approved.is_(False))
            .count()
        )

    def average_approved_rating(self, agent_id: int) -> float:
        result = (
            self._base_query(agent_id)
            .filter(AgentReview.is_approved.is_(True))
            .with_entities(func.avg(AgentReview.rating))
            .scalar()
        )
        if result is None:
            return 0.0
        return round(float(result), 1)

    def get_reviews_paginated(
        self,
        agent_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        rating: Optional[int] = None,
    ) -> Tuple[List[AgentReview], int]:
        query = self._base_query(agent_id)

        status_norm = (status or "all").strip().lower()
        if status_norm == "approved":
            query = query.filter(AgentReview.is_approved.is_(True))
        elif status_norm == "pending":
            query = query.filter(AgentReview.is_approved.is_(False))

        if rating is not None:
            query = query.filter(AgentReview.rating == rating)

        total = query.count()
        reviews = (
            query.order_by(AgentReview.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return reviews, total
