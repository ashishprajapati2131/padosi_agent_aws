from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.repositories.agent_notification_repository import AgentNotificationRepository
from fastapi_app.schemas.notifications import (
    NotificationListResponse, NotificationItem, MarkReadRequest, MarkReadResponse
)

router = APIRouter(
    prefix="/v1/agents/notifications",
    tags=["Notifications"]
)

@router.get("", response_model=NotificationListResponse)
def get_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    repo = AgentNotificationRepository(db)
    items, total = repo.get_paginated(current_agent.id, page=page, page_size=page_size)
    unread_count = repo.count_unread(current_agent.id)

    notification_list = [
        NotificationItem(
            id=n.id,
            title=n.title,
            body=n.body,
            is_read=n.is_read,
            created_at=n.created_at
        ) for n in items
    ]

    return NotificationListResponse(
        success=True,
        total=total,
        page=page,
        page_size=page_size,
        unread_count=unread_count,
        notifications=notification_list
    )

@router.post("/mark-read", response_model=MarkReadResponse)
def mark_notifications_read(
    payload: MarkReadRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    repo = AgentNotificationRepository(db)
    marked = repo.mark_as_read(current_agent.id, payload.notification_ids)
    return MarkReadResponse(
        success=True,
        marked_count=marked,
        message=f"{marked} notification(s) marked as read."
    )

@router.post("/mark-all-read", response_model=MarkReadResponse)
def mark_all_read(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    repo = AgentNotificationRepository(db)
    marked = repo.mark_as_read(current_agent.id, None)
    return MarkReadResponse(
        success=True,
        marked_count=marked,
        message="All notifications marked as read."
    )
