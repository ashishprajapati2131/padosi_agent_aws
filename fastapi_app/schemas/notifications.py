from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class NotificationItem(BaseModel):
    id: int
    title: str
    body: str
    is_read: bool
    created_at: Optional[datetime] = None

class NotificationListResponse(BaseModel):
    success: bool
    total: int
    page: int
    page_size: int
    unread_count: int
    notifications: List[NotificationItem]

class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[int]] = None

class MarkReadResponse(BaseModel):
    success: bool
    marked_count: int
    message: str
