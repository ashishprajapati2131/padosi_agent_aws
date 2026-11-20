from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.repositories.agent_review_repository import AgentReviewRepository
from fastapi_app.services.lock_unlock_service import LockUnlockService
from fastapi_app.schemas.reviews import ReviewsListResponse, ReviewItem

router = APIRouter(
    prefix="/v1/agents/reviews",
    tags=["Agent Reviews"],
)


def get_review_repository(db: Session = Depends(get_db)) -> AgentReviewRepository:
    return AgentReviewRepository(db)


@router.get("", response_model=ReviewsListResponse)
def list_agent_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(
        "all",
        description="Filter: approved | pending | all",
    ),
    rating: int = Query(None, ge=1, le=5, description="Filter by star rating 1-5"),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db),
    repo: AgentReviewRepository = Depends(get_review_repository),
):
    """
    Paginated list of the authenticated agent's customer reviews.
    Locked plans return an empty list with is_locked / unlock_hint (leads pattern).
    Does not expose reviewer email/mobile.
    """
    lock_service = LockUnlockService(db)
    access_map = lock_service.get_feature_access_map(current_agent)
    review_access = access_map.get("view_reviews", {})
    is_locked = bool(review_access.get("is_locked", False))
    unlock_hint = review_access.get("unlock_hint")

    approved_count = repo.count_approved(current_agent.id)
    pending_count = repo.count_pending(current_agent.id)
    average_rating = repo.average_approved_rating(current_agent.id)

    if is_locked:
        return ReviewsListResponse(
            success=True,
            total=0,
            page=page,
            page_size=page_size,
            average_rating=average_rating,
            approved_count=approved_count,
            pending_count=pending_count,
            reviews=[],
            is_locked=True,
            unlock_hint=unlock_hint,
        )

    reviews, total = repo.get_reviews_paginated(
        agent_id=current_agent.id,
        page=page,
        page_size=page_size,
        status=status,
        rating=rating,
    )
    items = [
        ReviewItem(
            id=r.id,
            reviewer_name=r.reviewer_name,
            rating=int(r.rating or 0),
            review=r.review,
            is_approved=bool(r.is_approved),
            created_at=r.created_at,
        )
        for r in reviews
    ]
    return ReviewsListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        average_rating=average_rating,
        approved_count=approved_count,
        pending_count=pending_count,
        reviews=items,
        is_locked=False,
        unlock_hint=None,
    )
