from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_agent
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.models.championship import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipRewardSlab,
    ChampionshipRewardClaim,
    ChampionshipSocialAction,
    ChampionshipScratchUnlock,
    ChampionshipGoogleReviewLog,
    ChampionshipFraudFlag,
    ChampionshipAuditLog,
)
from fastapi_app.schemas.championship import (
    ChampionshipDashboardResponse,
    UnlockProgressSchema,
    FunnelMetricsSchema,
    RewardSlabSchema,
    LeaderboardEntrySchema,
    LeaderboardResponse,
    AggregateStatsSchema,
    WhatsAppLanguageTemplatesSchema,
    WhatsAppTemplateSchema,
    WhatsAppShareRequest,
    WhatsAppShareResponse,
    RewardClaimRequest,
    RewardClaimResponse,
    SocialFollowRequest,
    ScratchRevealRequest,
    PublicLandingResponse,
    AdminCampaignSettingsRequest,
    AdminFinancialLiabilityResponse,
)
from fastapi_app.services.championship_service import (
    get_current_campaign,
    get_or_create_participant,
    get_agent_profile_completion,
    get_agent_review_count,
    get_participant_roadmap,
    get_leaderboard_data,
    get_campaign_aggregate_stats,
    refresh_leaderboard_cache,
    WHATSAPP_TEMPLATES,
    render_whatsapp_message,
    get_whatsapp_share_url,
    generate_qr_base64,
    generate_qr_bytes,
    format_inr,
)
from fastapi_app.config import settings

router = APIRouter(
    prefix="/v1/championship",
    tags=["Agent Referral Championship"]
)


# ---------------------------------------------------------
# Android Mobile App Endpoints (JWT Protected)
# ---------------------------------------------------------

@router.get("/dashboard", response_model=ChampionshipDashboardResponse)
def get_agent_championship_dashboard(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Agent Mobile App Championship Command Center:
    - Verifies unlock gate: Profile completion >= 80% AND Reviews >= 10.
    - Returns live funnel metrics, 7-tier reward roadmap, WhatsApp defaults, QR code, and Top 10 leaderboard.
    """
    campaign = get_current_campaign(db)
    participant = get_or_create_participant(db, current_agent.id, campaign)

    # 1. Unlock Gate Evaluation
    completion = get_agent_profile_completion(db, current_agent.id)
    review_count = get_agent_review_count(db, current_agent.id)

    unlock_cfg = campaign.unlock_config or {'min_profile_percent': 80, 'min_reviews': 10}
    min_profile = int(unlock_cfg.get('min_profile_percent', 80))
    min_reviews = int(unlock_cfg.get('min_reviews', 10))

    is_unlocked = (completion >= min_profile and review_count >= min_reviews)
    if is_unlocked and not participant.is_unlocked:
        participant.is_unlocked = True
        participant.profile_completed_at = datetime.utcnow()
        participant.reviews_completed_at = datetime.utcnow()
        db.commit()

    unlock_gate_data = UnlockProgressSchema(
        is_unlocked=is_unlocked,
        profile_completion_percent=completion,
        min_profile_percent=min_profile,
        review_count=review_count,
        min_reviews=min_reviews
    )

    # 2. Funnel Metrics
    invited_count = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.referrer_id == participant.id
    ).count()

    form_filled_count = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.referrer_id == participant.id,
        ChampionshipReferral.registration_state != 'started'
    ).count()

    paid_count = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.referrer_id == participant.id,
        ChampionshipReferral.registration_state.in_(['paid', 'active'])
    ).count()

    funnel_data = FunnelMetricsSchema(
        invited_count=invited_count,
        form_filled_count=form_filled_count,
        paid_count=paid_count,
        qualified_count=participant.qualifying_referrals_count
    )

    # 3. Roadmap & Next Target
    app_url = settings.APP_URL.rstrip('/')
    roadmap_data = get_participant_roadmap(db, participant)
    roadmap_items = []
    for item in roadmap_data['roadmap']:
        img_path = item.get('image_path', '')
        item['image_url'] = f"{app_url}/static/{img_path}" if img_path else None
        roadmap_items.append(RewardSlabSchema(**item))

    # 4. Referral URL & QR Code
    referral_url = f"{app_url}/agent-registration/join/{participant.referral_id}/"
    qr_base64 = generate_qr_base64(referral_url)
    qr_download_url = f"{app_url}/api/v1/championship/qr-code"

    # 5. WhatsApp Message Defaults
    pricing = campaign.pricing_config or {}
    dig_price = pricing.get('digital', {}).get('campaign_price', 999)
    prof_price = pricing.get('professional', {}).get('campaign_price', 4999)
    profile_url = f"{app_url}/agent/{current_agent.agent_slug or current_agent.id}/"

    default_text = render_whatsapp_message(
        WHATSAPP_TEMPLATES['en']['templates'][0]['text'],
        agent_name=current_agent.fullname,
        referral_link=referral_url,
        profile_link=profile_url,
        digital_price=dig_price,
        professional_price=prof_price
    )
    default_wa_url = get_whatsapp_share_url(default_text)

    # 6. Leaderboard & Stats
    top_10_raw = get_leaderboard_data(db, campaign, limit=10)
    top_10 = [LeaderboardEntrySchema(**item) for item in top_10_raw]
    agg_raw = get_campaign_aggregate_stats(db, campaign)
    agg_stats = AggregateStatsSchema(**agg_raw)

    # 7. Next Rank Differential
    next_rank_needed = 1
    if participant.current_rank and participant.current_rank > 1:
        prev_p = db.query(ChampionshipParticipant).filter(
            ChampionshipParticipant.campaign_id == campaign.id,
            ChampionshipParticipant.current_rank == participant.current_rank - 1
        ).first()
        if prev_p:
            diff = prev_p.qualifying_referrals_count - participant.qualifying_referrals_count
            next_rank_needed = max(1, diff + 1)

    days_left = 0
    if datetime.utcnow() < campaign.end_date:
        days_left = max(0, int((campaign.end_date - datetime.utcnow()).total_seconds() // 86400))

    return ChampionshipDashboardResponse(
        success=True,
        campaign_name=campaign.name,
        campaign_status=campaign.status,
        days_left=days_left,
        hero_image_url=f"{app_url}/static/championship/championship-hero.jpg",
        referral_id=participant.referral_id,
        referral_url=referral_url,
        qr_base64=qr_base64,
        qr_download_url=qr_download_url,
        unlock_gate=unlock_gate_data,
        funnel=funnel_data,
        roadmap=roadmap_items,
        next_reward_title=roadmap_data['next_reward_title'],
        referrals_needed_for_next_reward=roadmap_data['referrals_needed'],
        current_rank=participant.current_rank or 0,
        referrals_needed_to_beat_next_rank=next_rank_needed,
        top_10_leaderboard=top_10,
        aggregate_stats=agg_stats,
        default_whatsapp_text=default_text,
        default_whatsapp_url=default_wa_url
    )



@router.get("/leaderboard", response_model=LeaderboardResponse)
def get_championship_leaderboard(
    limit: int = Query(50, ge=1, le=100),
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Get full championship leaderboard (Top 50 by default).
    Privacy protection: Agent names are masked as 'First M.'
    """
    campaign = get_current_campaign(db)
    leaderboard_raw = get_leaderboard_data(db, campaign, limit=limit)
    entries = [LeaderboardEntrySchema(**item) for item in leaderboard_raw]

    total_participants = db.query(ChampionshipParticipant).filter(
        ChampionshipParticipant.campaign_id == campaign.id
    ).count()

    return LeaderboardResponse(
        success=True,
        campaign_id=campaign.id,
        campaign_name=campaign.name,
        total_participants=total_participants,
        leaderboard=entries
    )


@router.get("/whatsapp-templates")
def get_whatsapp_templates(
    lang: str = Query("en", description="Language code: en, hi, gu, mr, ta, te, bn, ml, kn"),
    current_agent: Agent = Depends(get_current_agent)
):
    """
    Get multi-lingual WhatsApp invitation templates (9 Indian Languages).
    """
    lang_code = lang.strip().lower()
    if lang_code not in WHATSAPP_TEMPLATES:
        lang_code = 'en'

    data = WHATSAPP_TEMPLATES[lang_code]
    return {
        "success": True,
        "language_code": lang_code,
        "label": data['label'],
        "templates": data['templates']
    }


@router.post("/whatsapp-share", response_model=WhatsAppShareResponse)
def generate_whatsapp_share_payload(
    payload: WhatsAppShareRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Generate custom WhatsApp message text and deep-link for Android share intent.
    """
    campaign = get_current_campaign(db)
    participant = get_or_create_participant(db, current_agent.id, campaign)

    app_url = settings.APP_URL.rstrip('/')
    referral_url = f"{app_url}/agent-registration/join/{participant.referral_id}/"
    profile_url = f"{app_url}/agent/{current_agent.agent_slug or current_agent.id}/"

    pricing = campaign.pricing_config or {}
    dig_price = pricing.get('digital', {}).get('campaign_price', 999)
    prof_price = pricing.get('professional', {}).get('campaign_price', 4999)

    lang_code = payload.language.strip().lower()
    if lang_code not in WHATSAPP_TEMPLATES:
        lang_code = 'en'

    # Find template by ID
    raw_template_text = None
    if payload.custom_message:
        raw_template_text = payload.custom_message
    else:
        for t in WHATSAPP_TEMPLATES[lang_code]['templates']:
            if t['id'] == payload.template_id:
                raw_template_text = t['text']
                break

    if not raw_template_text:
        raw_template_text = WHATSAPP_TEMPLATES['en']['templates'][0]['text']

    rendered = render_whatsapp_message(
        raw_template_text,
        agent_name=current_agent.fullname,
        referral_link=referral_url,
        profile_link=profile_url,
        digital_price=dig_price,
        professional_price=prof_price
    )
    wa_url = get_whatsapp_share_url(rendered)

    return WhatsAppShareResponse(
        success=True,
        rendered_message=rendered,
        whatsapp_url=wa_url
    )


@router.get("/qr-code")
def download_championship_qr(
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Download branded championship PNG QR code.
    """
    campaign = get_current_campaign(db)
    participant = get_or_create_participant(db, current_agent.id, campaign)
    app_url = settings.APP_URL.rstrip('/')
    referral_url = f"{app_url}/agent-registration/join/{participant.referral_id}/"

    qr_bytes = generate_qr_bytes(referral_url)
    return Response(
        content=qr_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="PadosiAgent_QR_{participant.referral_id}.png"'
        }
    )


@router.post("/claim-reward", response_model=RewardClaimResponse)
def claim_milestone_reward(
    payload: RewardClaimRequest,
    current_agent: Agent = Depends(get_current_agent),
    db: Session = Depends(get_db)
):
    """
    Claim unlocked milestone reward (e.g., Amazon or Flipkart voucher provider choice & shipping address).
    """
    campaign = get_current_campaign(db)
    participant = get_or_create_participant(db, current_agent.id, campaign)

    slab = db.query(ChampionshipRewardSlab).filter(
        ChampionshipRewardSlab.id == payload.slab_id,
        ChampionshipRewardSlab.campaign_id == campaign.id
    ).first()

    if not slab:
        raise HTTPException(status_code=404, detail="Reward slab not found.")

    if participant.qualifying_referrals_count < slab.threshold:
        raise HTTPException(status_code=400, detail=f"Referral threshold of {slab.threshold} not yet reached.")

    claim = db.query(ChampionshipRewardClaim).filter(
        ChampionshipRewardClaim.participant_id == participant.id,
        ChampionshipRewardClaim.reward_slab_id == slab.id
    ).first()

    if not claim:
        claim = ChampionshipRewardClaim(
            participant_id=participant.id,
            reward_slab_id=slab.id,
            status="processing"
        )
        db.add(claim)
    
    claim.status = "processing"
    claim.claim_data = {
        "voucher_provider": payload.voucher_provider,
        "shipping_address": payload.shipping_address or "",
        "claimed_at": datetime.utcnow().isoformat()
    }
    db.commit()

    return RewardClaimResponse(
        success=True,
        message=f'Reward claim for "{slab.title}" submitted successfully! Our team will dispatch your voucher/reward.',
        status="processing"
    )


# ---------------------------------------------------------
# Public Unauthenticated Endpoints (Landing & Visitor)
# ---------------------------------------------------------

@router.get("/public/landing/{ref_id}", response_model=PublicLandingResponse)
def get_public_referral_landing_details(
    ref_id: str,
    db: Session = Depends(get_db)
):
    """
    Public visitor details for referrer link (`/agent-registration/join/{ref_id}/`).
    """
    ref_id = ref_id.strip().upper()
    campaign = get_current_campaign(db)

    participant = db.query(ChampionshipParticipant).filter(
        ChampionshipParticipant.referral_id == ref_id,
        ChampionshipParticipant.campaign_id == campaign.id
    ).first()

    if not participant:
        participant = db.query(ChampionshipParticipant).filter(
            ChampionshipParticipant.campaign_id == campaign.id
        ).first()

    if not participant:
        raise HTTPException(status_code=404, detail="Referral code not found.")

    referring_agent = participant.agent
    prof = db.query(AgentProfile).filter(AgentProfile.agent_id == referring_agent.id).first()

    categories = ['Life Insurance', 'Health Insurance', 'Motor Insurance']
    if prof and prof.desired_services:
        if isinstance(prof.desired_services, list):
            categories = [str(s).strip().title() for s in prof.desired_services if str(s).strip()][:4]

    review_count = get_agent_review_count(db, referring_agent.id)
    city = prof.primary_city if prof and prof.primary_city else "India"

    pricing = campaign.pricing_config or {}
    dig_price = pricing.get('digital', {}).get('campaign_price', 999)
    prof_price = pricing.get('professional', {}).get('campaign_price', 4999)
    app_url = settings.APP_URL.rstrip('/')

    return PublicLandingResponse(
        success=True,
        campaign_name=campaign.name,
        referring_agent_name=referring_agent.fullname or "Insurance Advisor",
        referring_agent_city=city,
        referring_agent_rating=5.0,
        referring_agent_reviews_count=review_count,
        categories=categories,
        followed_platforms=[],
        is_scratched=False,
        is_50_unlocked=False,
        digital_campaign_price=dig_price,
        prof_campaign_price=prof_price,
        google_review_url=campaign.google_review_url or "https://g.page/r/padosiagent/review",
        registration_url=f"{app_url}/agent-registration?ref={ref_id}"
    )


@router.post("/public/social-follow")
def record_social_follow(
    payload: SocialFollowRequest,
    db: Session = Depends(get_db)
):
    """
    Record visitor social follow (Step 1).
    """
    platform = payload.platform.strip().lower()
    if not platform:
        raise HTTPException(status_code=400, detail="Platform required.")

    action = ChampionshipSocialAction(
        session_id=payload.session_id,
        platform=platform
    )
    db.add(action)
    db.commit()

    followed = db.query(ChampionshipSocialAction.platform).filter(
        ChampionshipSocialAction.session_id == payload.session_id
    ).all()
    followed_list = [f[0] for f in followed]

    scratch = db.query(ChampionshipScratchUnlock).filter(
        ChampionshipScratchUnlock.session_id == payload.session_id
    ).first()
    is_50_unlocked = bool(scratch and scratch.is_revealed and len(followed_list) >= 1)

    return {
        "success": True,
        "followed_platforms": followed_list,
        "is_50_unlocked": is_50_unlocked,
        "message": f"Thank you for following us on {platform.title()}!"
    }


@router.post("/public/scratch-reveal")
def record_scratch_reveal(
    payload: ScratchRevealRequest,
    db: Session = Depends(get_db)
):
    """
    Record visitor 25% scratch card reveal (Step 2).
    """
    scratch = db.query(ChampionshipScratchUnlock).filter(
        ChampionshipScratchUnlock.session_id == payload.session_id
    ).first()

    if not scratch:
        scratch = ChampionshipScratchUnlock(
            session_id=payload.session_id,
            is_revealed=True,
            revealed_discount_pct=25,
            final_unlocked_pct=50
        )
        db.add(scratch)
    else:
        scratch.is_revealed = True

    db.commit()

    followed = db.query(ChampionshipSocialAction).filter(
        ChampionshipSocialAction.session_id == payload.session_id
    ).count()

    is_50_unlocked = followed >= 1

    return {
        "success": True,
        "revealed": True,
        "discount_revealed": 25,
        "is_50_unlocked": is_50_unlocked,
        "message": "25% OFF Revealed! Complete social follow to unlock 50% Campaign Pricing!" if not is_50_unlocked else "50% OFF UNLOCKED 🎉"
    }


# ---------------------------------------------------------
# Administrative Endpoints
# ---------------------------------------------------------

@router.get("/admin/financial-liability", response_model=AdminFinancialLiabilityResponse)
def get_admin_financial_liability(
    db: Session = Depends(get_db)
):
    """
    Get financial & liability metrics for referral championship.
    """
    campaign = get_current_campaign(db)

    paid_refs = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.campaign_id == campaign.id,
        ChampionshipReferral.registration_state.in_(['paid', 'active'])
    ).all()

    pricing = campaign.pricing_config or {}
    dig_price = float(pricing.get('digital', {}).get('campaign_price', 999))
    prof_price = float(pricing.get('professional', {}).get('campaign_price', 4999))

    gross_revenue = len(paid_refs) * dig_price
    refunded_count = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.campaign_id == campaign.id,
        ChampionshipReferral.registration_state == 'refunded'
    ).count()

    refund_amount = refunded_count * dig_price
    net_revenue = gross_revenue - refund_amount

    # Potential reward liability calculation
    potential_liability = 0.0
    slabs = db.query(ChampionshipRewardSlab).filter(
        ChampionshipRewardSlab.campaign_id == campaign.id,
        ChampionshipRewardSlab.is_active == True
    ).all()

    for slab in slabs:
        qualified_agents = db.query(ChampionshipParticipant).filter(
            ChampionshipParticipant.campaign_id == campaign.id,
            ChampionshipParticipant.qualifying_referrals_count >= slab.threshold
        ).count()
        potential_liability += qualified_agents * float(slab.value or 0.0)

    claims = db.query(ChampionshipRewardClaim).all()
    current_liability = sum(float(c.reward_slab.value or 0.0) for c in claims if c.status in ['approved', 'processing'])
    rewards_issued = sum(float(c.reward_slab.value or 0.0) for c in claims if c.status in ['dispatched', 'delivered', 'redeemed'])

    health_status = "SAFE"
    health_color = "success"
    if net_revenue < potential_liability:
        health_status = "LIMIT EXCEEDED"
        health_color = "danger"
    elif net_revenue <= (potential_liability * 1.5):
        health_status = "WATCH"
        health_color = "warning"

    total_participants = db.query(ChampionshipParticipant).filter(
        ChampionshipParticipant.campaign_id == campaign.id
    ).count()

    total_qualifying = db.query(ChampionshipReferral).filter(
        ChampionshipReferral.campaign_id == campaign.id,
        ChampionshipReferral.is_qualifying == True
    ).count()

    fraud_flags_count = db.query(ChampionshipFraudFlag).filter(
        ChampionshipFraudFlag.status == 'flagged'
    ).count()

    return AdminFinancialLiabilityResponse(
        success=True,
        campaign_name=campaign.name,
        gross_revenue=gross_revenue,
        refund_amount=refund_amount,
        net_revenue=net_revenue,
        digital_paid_count=len(paid_refs),
        prof_paid_count=0,
        potential_liability=potential_liability,
        current_liability=current_liability,
        rewards_issued=rewards_issued,
        health_status=health_status,
        health_color=health_color,
        total_participants=total_participants,
        total_qualifying=total_qualifying,
        fraud_flags_count=fraud_flags_count
    )


@router.post("/admin/settings")
def update_admin_campaign_settings(
    payload: AdminCampaignSettingsRequest,
    db: Session = Depends(get_db)
):
    """
    Update campaign status, dynamic pricing, and unlock thresholds.
    """
    campaign = get_current_campaign(db)

    if payload.status:
        campaign.status = payload.status

    campaign.pricing_config = {
        "digital": {
            "regular_price": payload.digital_regular_price,
            "campaign_price": payload.digital_campaign_price,
            "renewal_price": payload.digital_renewal_price,
            "name": "Digital Visibility"
        },
        "professional": {
            "regular_price": payload.prof_regular_price,
            "campaign_price": payload.prof_campaign_price,
            "renewal_price": payload.prof_renewal_price,
            "name": "Professional Visibility"
        },
        "discount_percent": 50
    }

    campaign.unlock_config = {
        "min_profile_percent": payload.min_profile_percent,
        "min_reviews": payload.min_reviews
    }

    if payload.google_review_url:
        campaign.google_review_url = payload.google_review_url

    if payload.instagram_url or payload.facebook_url:
        campaign.social_channels = [
            {"platform": "instagram", "name": "Instagram", "url": payload.instagram_url or "https://instagram.com/padosiagent", "icon": "fa-instagram"},
            {"platform": "facebook", "name": "Facebook", "url": payload.facebook_url or "https://facebook.com/padosiagent", "icon": "fa-facebook-f"}
        ]

    db.commit()

    return {
        "success": True,
        "message": "Referral championship settings updated successfully!"
    }
