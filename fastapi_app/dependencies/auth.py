from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.utils.auth import decode_access_token
from app.repositories.user_repository import UserRepository
from app.repositories.agent_repository import AgentRepository
from app.models.agent import Agent
from app.models.user import User
from jose.exceptions import ExpiredSignatureError, JWTError

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_access_token(token)
        email: str = payload.get("sub")
        role: str = payload.get("role")
        jti: str = payload.get("jti")
        if email is None or role != "agent":
            raise credentials_exception
            
        if jti:
            from app.models.user_token import UserToken
            token_record = db.query(UserToken).filter(UserToken.jti == jti).first()
            if not token_record or token_record.is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token is invalid or has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise credentials_exception
        
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(email)
    if user is None:
        raise credentials_exception
        
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user account"
        )
        
    return user

def get_current_agent(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Agent:
    agent_repo = AgentRepository(db)
    agent = agent_repo.get_by_email(current_user.email)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found."
        )
        
    return agent
