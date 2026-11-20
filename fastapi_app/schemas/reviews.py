from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class ReviewItem(BaseModel):
    id: int
    reviewer_name: Optional[str] = None
    rating: int
    review: Optional[str] = None
    is_approved: bool
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewsListResponse(BaseModel):
    success: bool
    total: int
    page: int
    page_size: int
    average_rating: float = 0.0
    approved_count: int = 0
    pending_count: int = 0
    reviews: List[ReviewItem]
    is_locked: bool = False
    unlock_hint: Optional[str] = None
