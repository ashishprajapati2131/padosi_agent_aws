from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi_app.models.agent_device_token import AgentDeviceToken

class AgentDeviceTokenRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_tokens_for_agent(self, agent_id: int) -> List[str]:
        return [
            row[0] for row in self.db.query(AgentDeviceToken.token).filter(
                AgentDeviceToken.agent_id == agent_id,
                AgentDeviceToken.token.isnot(None),
                AgentDeviceToken.token != ""
            ).all()
        ]

    def upsert_token(self, agent_id: int, token: str, platform: Optional[str] = "android") -> AgentDeviceToken:
        token_record = self.db.query(AgentDeviceToken).filter(
            AgentDeviceToken.token == token
        ).first()

        now = datetime.utcnow()
        if token_record:
            token_record.agent_id = agent_id
            token_record.platform = platform or token_record.platform
            token_record.last_seen_at = now
        else:
            token_record = AgentDeviceToken(
                agent_id=agent_id,
                token=token,
                platform=platform or "android",
                last_seen_at=now
            )
            self.db.add(token_record)

        self.db.commit()
        self.db.refresh(token_record)
        return token_record

    def delete_token(self, token: str) -> bool:
        record = self.db.query(AgentDeviceToken).filter(AgentDeviceToken.token == token).first()
        if record:
            self.db.delete(record)
            self.db.commit()
            return True
        return False
