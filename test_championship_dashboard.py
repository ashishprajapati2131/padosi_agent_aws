import sys
import os
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime

os.environ["CLOUDINARY_CLOUD_NAME"] = "test"
os.environ["CLOUDINARY_API_KEY"] = "test"
os.environ["CLOUDINARY_API_SECRET"] = "test"

from fastapi_app.database import Base
from fastapi_app.main import app
from fastapi_app.database import get_db

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

import fastapi_app.models
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app, raise_server_exceptions=True)

db = TestingSessionLocal()
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile

agent = Agent(fullname="Test Agent", email="test@test.com", mobile="9876543210", agent_pincode="380001")
db.add(agent)
db.commit()
db.refresh(agent)

profile = AgentProfile(
    agent_id=agent.id,
    display_name="Test Agent",
    profile_photo_path="test_agent.jpg",
    address="123 Test Street",
    languages="English, Hindi"
)
db.add(profile)
db.commit()

from fastapi_app.dependencies.auth import get_current_agent
def override_get_current_agent():
    return agent
app.dependency_overrides[get_current_agent] = override_get_current_agent

response = client.get("/v1/championship/dashboard")
print("Status Code:", response.status_code)
if response.status_code == 200:
    data = response.json()
    print("Success: True")
    print(f"Campaign Name: {data.get('campaign_name')}")
    print(f"Profile Completion: {data.get('unlock_gate', {}).get('profile_completion_percent')}%")
    print(f"Roadmap tiers: {len(data.get('roadmap', []))}")
    assert data["success"] is True
    assert "referral_id" in data
    assert len(data["roadmap"]) > 0
    print("All assertions passed!")
else:
    print("Failed:", response.text)
