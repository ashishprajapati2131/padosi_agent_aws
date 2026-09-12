from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from fastapi_app.models.agent_notification import AgentNotification

class AgentNotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_unread(self, agent_id: int) -> List[AgentNotification]:
        return self.db.query(AgentNotification).filter(
            AgentNotification.agent_id == agent_id,
            AgentNotification.is_read == False
        ).order_by(AgentNotification.created_at.desc()).all()

    def count_unread(self, agent_id: int) -> int:
        return self.db.query(AgentNotification).filter(
            AgentNotification.agent_id == agent_id,
            AgentNotification.is_read == False
        ).count()

    def get_paginated(self, agent_id: int, page: int = 1, page_size: int = 20) -> Tuple[List[AgentNotification], int]:
        query = self.db.query(AgentNotification).filter(
            AgentNotification.agent_id == agent_id
        )
        total = query.count()
        offset = (page - 1) * page_size
        notifications = query.order_by(AgentNotification.created_at.desc()).offset(offset).limit(page_size).all()
        return notifications, total

    def mark_as_read(self, agent_id: int, notification_ids: Optional[List[int]] = None) -> int:
        query = self.db.query(AgentNotification).filter(
            AgentNotification.agent_id == agent_id,
            AgentNotification.is_read == False
        )
        if notification_ids:
            query = query.filter(AgentNotification.id.in_(notification_ids))
        
        updated_count = query.update({"is_read": True}, synchronize_session=False)
        self.db.commit()
        return updated_count
