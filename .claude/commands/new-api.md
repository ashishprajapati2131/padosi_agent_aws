# /new-api — Add a new FastAPI endpoint

## Instructions for Claude

FastAPI is mounted at `/api` and serves the mobile app.

## File structure to follow
```
fastapi_app/
├── routers/<name>.py        ← APIRouter with endpoints
├── schemas/<name>.py        ← Pydantic request/response models  
├── services/<name>_service.py ← Business logic
└── repositories/<name>_repository.py ← DB queries (SQLAlchemy)
```

## Standard router template
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent

router = APIRouter(prefix="/v1/<name>", tags=["<name>"])

@router.get("/")
def list_items(db: Session = Depends(get_db), agent = Depends(get_current_agent)):
    # ...
```

## After creating router
Add to `fastapi_app/main.py`:
```python
from fastapi_app.routers import <name>
app.include_router(<name>.router)
```

## Auth in FastAPI
- Protected: `agent = Depends(get_current_agent)` — extracts agent from JWT Bearer token
- Public: no dependency

## Database in FastAPI
- SQLAlchemy session via `db: Session = Depends(get_db)`
- Same MySQL database as Django
- Tables are shared — column names must match Django model field `db_column` or default snake_case
