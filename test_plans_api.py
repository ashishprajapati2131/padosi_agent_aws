import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["CLOUDINARY_CLOUD_NAME"] = "test"
os.environ["CLOUDINARY_API_KEY"] = "test"
os.environ["CLOUDINARY_API_SECRET"] = "test"

from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi_app.database import Base, get_db
from fastapi_app.main import app
import fastapi_app.models
from fastapi_app.models.agent import Agent
from fastapi_app.models.user import User
from fastapi_app.models.subscription_plan import SubscriptionPlan
from fastapi_app.models.site_setting import SiteSetting
from fastapi_app.models.referral_code import ReferralCode
from fastapi_app.dependencies.auth import get_optional_agent
from fastapi_app.utils.auth import create_access_token

# Setup in-memory SQLite engine
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=True)

def test_plans_endpoint():
    db = TestingSessionLocal()

    # 1. Seed Subscription Plans
    starter = SubscriptionPlan(
        name="Starter",
        slug="starter",
        description="Ideal for new agents starting digital presence",
        color_theme="starter-theme",
        badge_text="Most Popular for Beginners",
        sort_order=1,
        actual_price=1180.0,
        discounted_price=799.0,
        show_profile_section=True,
        is_listed_in_directory=True,
        show_performance_stats=True,
        show_sales_insights=False,
        show_new_business_leads=True,
        show_recent_leads=True,
        is_active=True
    )
    pro = SubscriptionPlan(
        name="Professional",
        slug="professional",
        description="For ambitious advisors wanting full visibility & direct leads",
        color_theme="pro-theme",
        badge_text="Best Value",
        sort_order=2,
        actual_price=2360.0,
        discounted_price=1499.0,
        show_profile_section=True,
        is_listed_in_directory=True,
        show_performance_stats=True,
        show_sales_insights=True,
        show_new_business_leads=True,
        show_recent_leads=True,
        show_agent_certificate=True,
        show_career_timeline=True,
        show_professional_bio=True,
        show_portfolio=True,
        is_active=True
    )
    exclusive = SubscriptionPlan(
        name="Exclusive Partner",
        slug="exclusive",
        description="Top-tier advisor package with exclusive territory visibility",
        color_theme="exclusive-theme",
        badge_text="VIP Club",
        sort_order=3,
        actual_price=5900.0,
        discounted_price=3999.0,
        show_profile_section=True,
        is_listed_in_directory=True,
        show_performance_stats=True,
        show_sales_insights=True,
        show_new_business_leads=True,
        show_recent_leads=True,
        show_agent_certificate=True,
        show_career_timeline=True,
        show_professional_bio=True,
        show_portfolio=True,
        show_claim_support=True,
        show_companies=True,
        show_achievement=True,
        show_review_management=True,
        show_rank_boost_tips=True,
        is_active=True
    )
    db.add_all([starter, pro, exclusive])

    # Seed SiteSetting for default trial discount
    trial_setting = SiteSetting(
        key="trial_upgrade_discount",
        value="25",
        group="pricing"
    )
    db.add(trial_setting)

    # Seed an Agent on Trial
    user = User(
        fullname="Trial Advisor",
        email="trial@example.com",
        password="fake",
        role="agent",
        status="active"
    )
    db.add(user)
    db.flush()

    trial_agent = Agent(
        user_id=user.id,
        fullname="Trial Advisor",
        email=user.email,
        mobile="9876543210",
        agent_pincode="380001",
        status="active",
        plan_type="free_trial",
        trial_ends_at=datetime.utcnow() + timedelta(days=5),
        upgrade_discount_percent=30 # higher than default 25%
    )
    db.add(trial_agent)

    # Seed an Agent on Professional's Plan
    user_pro = User(
        fullname="Pro Advisor",
        email="pro@example.com",
        password="fake",
        role="agent",
        status="active"
    )
    db.add(user_pro)
    db.flush()

    pro_agent = Agent(
        user_id=user_pro.id,
        fullname="Pro Advisor",
        email=user_pro.email,
        mobile="9876543211",
        agent_pincode="380002",
        status="active",
        plan_type="professional",
    )
    db.add(pro_agent)

    db.commit()

    print("\n================== TEST 1: Unauthenticated Guest ==================")
    resp = client.get("/v1/agents/plans")
    assert resp.status_code == 200, f"Failed: {resp.text}"
    body = resp.json()
    assert body["success"] is True
    assert len(body["plans"]) == 2
    assert {p["slug"] for p in body["plans"]} == {"starter", "professional"}
    assert body["agent_current_plan"] is None
    assert body["upgrade_discount"] is None

    # Check GST calculations for Starter's Plan
    starter_plan = next(p for p in body["plans"] if p["slug"] == "starter")
    p_info = starter_plan["pricing"]
    print(f"Starter Pricing: Actual={p_info['actual_price']}, Disc={p_info['discounted_price']}, BaseExclGST={p_info['base_price_exclusive_gst']}, GST={p_info['gst_amount']}, Final={p_info['final_price_inclusive_gst']}")
    assert starter_plan["is_current_plan"] is False
    assert p_info["actual_price"] == 1999.0
    assert p_info["display_price"] == 1999.0
    assert p_info["formatted_final_price"] == "₹1,999"
    assert p_info["scratch_revealed"] is False
    assert p_info["gst_amount"] == 359.82
    assert p_info["final_price_inclusive_gst"] == 2359.0
    pro_guest = next(p for p in body["plans"] if p["slug"] == "professional")
    assert pro_guest["pricing"]["actual_price"] == 9999.0
    assert pro_guest["pricing"]["display_price"] == 9999.0
    assert pro_guest["pricing"]["formatted_final_price"] == "₹9,999"
    print("[PASS] Test 1 passed!")

    print("\n================== TEST 2: Authenticated Trial Agent ==================")
    from fastapi_app.models.user_token import UserToken
    jti_trial = "trial-agent-jti-12345"
    db.add(UserToken(
        jti=jti_trial,
        user_id=user.id,
        is_revoked=False,
        expires_at=datetime.utcnow() + timedelta(days=1)
    ))
    db.commit()

    token = create_access_token(data={"sub": trial_agent.email, "role": "agent", "user_id": user.id, "jti": jti_trial})
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/v1/agents/plans", headers=headers)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    body = resp.json()

    print("Agent Current Plan:", body["agent_current_plan"])
    assert body["agent_current_plan"]["is_on_trial"] is True
    assert body["agent_current_plan"]["trial_days_left"] >= 4

    print("Upgrade Discount:", body["upgrade_discount"])
    # Agent has 30% discount set
    assert body["upgrade_discount"]["applicable_discount_pct"] == 30
    assert "30%" in body["upgrade_discount"]["offer_message"]

    # The 30% trial offer stays in upgrade_discount. The card price is the admin list price.
    pro_plan = next(p for p in body["plans"] if p["slug"] == "professional")
    print(f"Professional's Plan for Trial Agent: Display = Rs. {pro_plan['pricing']['display_price']}")
    assert pro_plan["pricing"]["display_price"] == 9999.0
    assert pro_plan["pricing"]["agent_discount_pct"] == 0
    assert pro_plan["pricing"]["final_price_inclusive_gst"] == 11799.0
    print("[PASS] Test 2 passed!")

    print("\n================== TEST 2b: Scratch and follow ==================")
    missing = client.post("/v1/agents/plans/scratch", json={"plan_slug": "starter"})
    assert missing.status_code in (401, 403)
    no_auth = client.post(
        "/v1/agents/plans/scratch",
        json={"plan_slug": "starter"},
        headers={"Authorization": "Bearer not-a-token"},
    )
    assert no_auth.status_code == 401

    bad = client.post("/v1/agents/plans/scratch", json={"plan_slug": "exclusive"}, headers=headers)
    assert bad.status_code == 400
    unknown = client.post("/v1/agents/plans/follow", json={"platform": "myspace"}, headers=headers)
    assert unknown.status_code == 400

    followed = client.post("/v1/agents/plans/follow", json={"platform": "Instagram"}, headers=headers)
    assert followed.status_code == 200, followed.text
    starter_after_follow = next(p for p in followed.json()["plans"] if p["slug"] == "starter")
    assert starter_after_follow["pricing"]["display_price"] == 1999.0
    assert starter_after_follow["pricing"]["price_after_scratch"] == 1399.0
    assert starter_after_follow["pricing"]["follow_count"] == 1
    assert followed.json()["followed_platforms"] == ["instagram"]

    again = client.post("/v1/agents/plans/follow", json={"platform": "instagram"}, headers=headers)
    assert again.json()["followed_platforms"] == ["instagram"]

    scratched = client.post("/v1/agents/plans/scratch", json={"plan_slug": "basic"}, headers=headers)
    assert scratched.status_code == 200, scratched.text
    starter_scratched = next(p for p in scratched.json()["plans"] if p["slug"] == "starter")
    assert starter_scratched["pricing"]["scratch_revealed"] is True
    assert starter_scratched["pricing"]["display_price"] == 1399.0
    assert starter_scratched["pricing"]["final_price_inclusive_gst"] == 1651.0
    pro_unscratched = next(p for p in scratched.json()["plans"] if p["slug"] == "professional")
    assert pro_unscratched["pricing"]["display_price"] == 9999.0
    assert pro_unscratched["pricing"]["price_after_scratch"] == 7899.0

    for platform in ("facebook", "youtube", "linkedin"):
        step = client.post("/v1/agents/plans/follow", json={"platform": platform}, headers=headers)
        assert step.status_code == 200, step.text
    four = step.json()
    starter_four = next(p for p in four["plans"] if p["slug"] == "starter")
    assert starter_four["pricing"]["follow_count"] == 4
    assert starter_four["pricing"]["display_price"] == 999.0
    assert starter_four["pricing"]["final_price_inclusive_gst"] == 1179.0

    import json as _json
    db.add(SiteSetting(
        key="pricing_config",
        value=_json.dumps({
            "starter": {"full_price": 1888, "scratch_price": 1000, "scratch_enabled": True},
            "professional": {"full_price": 8888, "scratch_price": 7000, "scratch_enabled": True},
            "social_discount_active": False,
        }),
        group="pricing",
    ))
    db.commit()
    custom = client.get("/v1/agents/plans", headers=headers)
    custom_starter = next(p for p in custom.json()["plans"] if p["slug"] == "starter")
    custom_pro = next(p for p in custom.json()["plans"] if p["slug"] == "professional")
    assert custom_starter["pricing"]["display_price"] == 1000.0
    assert custom_pro["pricing"]["display_price"] == 8888.0
    db.query(SiteSetting).filter(SiteSetting.key == "pricing_config").delete()
    db.commit()
    print("[PASS] Test 2b passed!")

    print("\n================== TEST 3: Authenticated Pro Plan Agent ==================")
    jti_pro = "pro-agent-jti-67890"
    db.add(UserToken(
        jti=jti_pro,
        user_id=user_pro.id,
        is_revoked=False,
        expires_at=datetime.utcnow() + timedelta(days=1)
    ))
    db.commit()

    token_pro = create_access_token(data={"sub": pro_agent.email, "role": "agent", "user_id": user_pro.id, "jti": jti_pro})
    headers_pro = {"Authorization": f"Bearer {token_pro}"}

    resp = client.get("/v1/agents/plans", headers=headers_pro)
    assert resp.status_code == 200, f"Failed: {resp.text}"
    body = resp.json()

    pro_plan_item = next(p for p in body["plans"] if p["slug"] == "professional")
    starter_plan_item = next(p for p in body["plans"] if p["slug"] == "starter")

    print(f"Professional is_current_plan: {pro_plan_item['is_current_plan']}")
    print(f"Starter is_current_plan: {starter_plan_item['is_current_plan']}")
    assert pro_plan_item["is_current_plan"] is True
    assert starter_plan_item["is_current_plan"] is False
    print("[PASS] Test 3 passed!")

    print("\n================== TEST 4: Referral Reward Pro 1 Rs ==================")
    # Update trial agent with referral_reward_type = 'pro_plan_1rs'
    trial_agent.referral_reward_type = "pro_plan_1rs"
    db.commit()

    resp = client.get("/v1/agents/plans", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    pro_plan_reward = next(p for p in body["plans"] if p["slug"] == "professional")
    print(f"Pro Plan under Referral Reward: Final Incl GST = Rs. {pro_plan_reward['pricing']['final_price_inclusive_gst']}")
    assert pro_plan_reward["pricing"]["final_price_inclusive_gst"] == 1.0
    print("[PASS] Test 4 passed!")

    db.close()
    print("\n>>> ALL TESTS COMPLETED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    test_plans_endpoint()
