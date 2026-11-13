import secrets
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from urllib.parse import quote

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.referral_code import ReferralCode
from fastapi_app.models.referral_usage import ReferralUsage
from fastapi_app.config import settings

router = APIRouter(
    prefix="/v1/agents/referral",
    tags=["Referral Program"]
)

@router.get("")
def get_referral_details(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get the agent's referral dashboard, milestones, code, share links, and conversions.
    """
    ref_code = db.query(ReferralCode).filter(ReferralCode.agent_id == current_agent.id).first()
    if not ref_code:
        agent_id = current_agent.id
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(5):
            ref_code = ReferralCode(
                agent_id=agent_id,
                code=''.join(secrets.choice(alphabet) for _ in range(8)),
                is_active=True,
                total_referrals=0
            )
            db.add(ref_code)
            try:
                db.commit()
                db.refresh(ref_code)
                break
            except IntegrityError:
                # Code taken, or a parallel request already created this agent's code.
                db.rollback()
                ref_code = db.query(ReferralCode).filter(ReferralCode.agent_id == agent_id).first()
                if ref_code:
                    break
        if not ref_code:
            raise HTTPException(status_code=503, detail="Could not create your referral code. Please try again.")

    # Sync conversions
    converted_count = db.query(ReferralUsage).filter(
        ReferralUsage.referral_code_id == ref_code.id,
        ReferralUsage.status == "converted"
    ).count()

    if ref_code.total_referrals != converted_count:
        ref_code.total_referrals = converted_count
        db.commit()

    registered_count = db.query(Agent).filter(
        Agent.referred_by_code == ref_code.code
    ).count()

    pending_count = max(0, registered_count - converted_count)

    current_tier = ref_code.current_tier()
    next_tier = ref_code.next_tier()

    app_url = settings.APP_URL.rstrip('/')
    share_url = f"{app_url}/join/{ref_code.code}/"
    share_text = f"Join PadosiAgent - India's Trusted Insurance Agent Network using my referral code {ref_code.code}: {share_url}"

    tiers = [
        {"min": 1, "max": 2, "reward": "discount_25", "discount": 25, "label": "Tier 1: 25% Off"},
        {"min": 3, "max": 4, "reward": "discount_50", "discount": 50, "label": "Tier 2: 50% Off"},
        {"min": 5, "max": 999, "reward": "pro_plan_1rs", "discount": 99, "label": "Tier 3: Pro Plan @ ₹1"}
    ]

    return {
        "success": True,
        "referral_code": ref_code.code,
        "total_referrals": converted_count,
        "registered_referrals": registered_count,
        "pending_referrals": pending_count,
        "current_tier": current_tier,
        "next_tier": next_tier,
        "tiers": tiers,
        "share_url": share_url,
        "share_text": share_text,
        "whatsapp_url": f"https://api.whatsapp.com/send?text={quote(share_text)}"
    }
