from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, JSON, Numeric, Date, Float
)
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base


class ChampionshipCampaign(Base):
    __tablename__ = "championship_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), default="PadosiAgent Referral Championship")
    slug = Column(String(100), unique=True, default="championship-2026", index=True)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=False)
    status = Column(String(50), default="live")
    is_active = Column(Boolean, default=True)

    pricing_config = Column(JSON, default=dict)
    unlock_config = Column(JSON, default=dict)
    social_channels = Column(JSON, default=list)
    google_review_url = Column(String(500), default="https://g.page/r/padosiagent/review")
    rules = Column(Text, default="First valid referral attribution wins. Verified and Paid accounts count as qualifying.")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants = relationship("ChampionshipParticipant", back_populates="campaign", cascade="all, delete-orphan")
    reward_slabs = relationship("ChampionshipRewardSlab", back_populates="campaign", cascade="all, delete-orphan")


class ChampionshipParticipant(Base):
    __tablename__ = "championship_participants"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("championship_campaigns.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    referral_id = Column(String(50), unique=True, nullable=False, index=True)
    is_unlocked = Column(Boolean, default=False)
    profile_completed_at = Column(DateTime, nullable=True)
    reviews_completed_at = Column(DateTime, nullable=True)

    qualifying_referrals_count = Column(Integer, default=0, index=True)
    current_rank = Column(Integer, default=0, index=True)
    last_qualification_time = Column(DateTime, nullable=True)

    is_fraud_blocked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("ChampionshipCampaign", back_populates="participants")
    agent = relationship("Agent")
    referrals = relationship("ChampionshipReferral", back_populates="referrer", foreign_keys="ChampionshipReferral.referrer_id")
    claims = relationship("ChampionshipRewardClaim", back_populates="participant", cascade="all, delete-orphan")


class ChampionshipReferral(Base):
    __tablename__ = "championship_referrals"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("championship_campaigns.id", ondelete="CASCADE"), nullable=False)
    referrer_id = Column(Integer, ForeignKey("championship_participants.id", ondelete="CASCADE"), nullable=False)
    referred_agent_id = Column(Integer, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)

    referral_id = Column(String(50), nullable=False, index=True)
    session_id = Column(String(255), nullable=True)
    utm_params = Column(JSON, default=dict)
    registration_state = Column(String(50), default="started")
    is_qualifying = Column(Boolean, default=False, index=True)
    qualified_at = Column(DateTime, nullable=True)
    fraud_flag = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("ChampionshipCampaign")
    referrer = relationship("ChampionshipParticipant", back_populates="referrals", foreign_keys=[referrer_id])
    referred_agent = relationship("Agent", foreign_keys=[referred_agent_id])


class ChampionshipRewardSlab(Base):
    __tablename__ = "championship_reward_slabs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("championship_campaigns.id", ondelete="CASCADE"), nullable=False)
    threshold = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    reward_type = Column(String(50), nullable=False)
    badge_icon = Column(String(100), default="fa-gift")
    value = Column(Numeric(10, 2), default=0.00)
    winner_limit = Column(Integer, default=0)
    dispatch_date_default = Column(Date, nullable=True)
    order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("ChampionshipCampaign", back_populates="reward_slabs")
    claims = relationship("ChampionshipRewardClaim", back_populates="reward_slab", cascade="all, delete-orphan")


class ChampionshipRewardClaim(Base):
    __tablename__ = "championship_reward_claims"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("championship_participants.id", ondelete="CASCADE"), nullable=False)
    reward_slab_id = Column(Integer, ForeignKey("championship_reward_slabs.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), default="unlocked")
    claim_data = Column(JSON, default=dict)

    courier_name = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    dispatch_date = Column(Date, nullable=True)
    delivered_date = Column(Date, nullable=True)
    admin_notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participant = relationship("ChampionshipParticipant", back_populates="claims")
    reward_slab = relationship("ChampionshipRewardSlab", back_populates="claims")


class ChampionshipSocialAction(Base):
    __tablename__ = "championship_social_actions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    participant_id = Column(Integer, ForeignKey("championship_participants.id", ondelete="SET NULL"), nullable=True)
    platform = Column(String(50), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)


class ChampionshipScratchUnlock(Base):
    __tablename__ = "championship_scratch_unlocks"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    draft_id = Column(Integer, nullable=True)
    is_revealed = Column(Boolean, default=False)
    revealed_discount_pct = Column(Integer, default=25)
    final_unlocked_pct = Column(Integer, default=50)
    unlocked_at = Column(DateTime, default=datetime.utcnow)


class ChampionshipGoogleReviewLog(Base):
    __tablename__ = "championship_google_review_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), index=True, nullable=False)
    prompt_shown_at = Column(DateTime, default=datetime.utcnow)
    link_clicked_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)


class ChampionshipFraudFlag(Base):
    __tablename__ = "championship_fraud_flags"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("championship_participants.id", ondelete="CASCADE"), nullable=False)
    referral_id = Column(Integer, ForeignKey("championship_referrals.id", ondelete="SET NULL"), nullable=True)
    reason = Column(String(255), nullable=False)
    details = Column(Text, default="")
    status = Column(String(50), default="flagged")
    flagged_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participant = relationship("ChampionshipParticipant")


class ChampionshipAuditLog(Base):
    __tablename__ = "championship_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("championship_campaigns.id", ondelete="SET NULL"), nullable=True)
    admin_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(255), nullable=False)
    old_value = Column(JSON, default=dict)
    new_value = Column(JSON, default=dict)
    reason = Column(Text, default="")
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChampionshipLeaderboardCache(Base):
    __tablename__ = "championship_leaderboard_cache"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("championship_campaigns.id", ondelete="CASCADE"), nullable=False)
    participant_id = Column(Integer, ForeignKey("championship_participants.id", ondelete="CASCADE"), nullable=False)
    rank = Column(Integer, nullable=False, index=True)
    referral_count = Column(Integer, nullable=False, index=True)
    tie_breaker_ts = Column(DateTime, nullable=True)
    is_frozen = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign = relationship("ChampionshipCampaign")
    participant = relationship("ChampionshipParticipant")
