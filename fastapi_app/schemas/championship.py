from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime, date


class UnlockProgressSchema(BaseModel):
    is_unlocked: bool
    profile_completion_percent: int
    min_profile_percent: int = 80
    review_count: int
    min_reviews: int = 10


class FunnelMetricsSchema(BaseModel):
    invited_count: int
    form_filled_count: int
    paid_count: int
    qualified_count: int


class RewardSlabSchema(BaseModel):
    id: int
    threshold: int
    title: str
    description: Optional[str] = ""
    reward_type: str
    badge_icon: str
    value: float
    value_formatted: str
    is_reached: bool
    is_unlocked: bool
    is_current_target: bool
    progress_percent: int
    referrals_needed: int
    claim_status: str


class LeaderboardEntrySchema(BaseModel):
    rank: int
    agent_name: str
    city: str
    referral_count: int
    referral_id: str


class AggregateStatsSchema(BaseModel):
    total_participants: int
    total_paid: int
    total_qualified: int
    total_referrals: int


class ChampionshipDashboardResponse(BaseModel):
    success: bool = True
    campaign_name: str
    campaign_status: str
    days_left: int
    referral_id: str
    referral_url: str
    qr_base64: str
    unlock_gate: UnlockProgressSchema
    funnel: FunnelMetricsSchema
    roadmap: List[RewardSlabSchema]
    next_reward_title: str
    referrals_needed_for_next_reward: int
    current_rank: int
    referrals_needed_to_beat_next_rank: int
    top_10_leaderboard: List[LeaderboardEntrySchema]
    aggregate_stats: AggregateStatsSchema
    default_whatsapp_text: str
    default_whatsapp_url: str


class LeaderboardResponse(BaseModel):
    success: bool = True
    campaign_id: int
    campaign_name: str
    total_participants: int
    leaderboard: List[LeaderboardEntrySchema]


class WhatsAppTemplateSchema(BaseModel):
    id: str
    title: str
    text: str


class WhatsAppLanguageTemplatesSchema(BaseModel):
    language_code: str
    label: str
    templates: List[WhatsAppTemplateSchema]


class WhatsAppShareRequest(BaseModel):
    language: str = "en"
    template_id: str = "en_1"
    custom_message: Optional[str] = None


class WhatsAppShareResponse(BaseModel):
    success: bool = True
    rendered_message: str
    whatsapp_url: str


class RewardClaimRequest(BaseModel):
    slab_id: int
    voucher_provider: str = Field("amazon", description="amazon or flipkart")
    shipping_address: Optional[str] = ""


class RewardClaimResponse(BaseModel):
    success: bool = True
    message: str
    status: str


class SocialFollowRequest(BaseModel):
    session_id: str
    platform: str


class ScratchRevealRequest(BaseModel):
    session_id: str


class PublicLandingResponse(BaseModel):
    success: bool = True
    campaign_name: str
    referring_agent_name: str
    referring_agent_city: str
    referring_agent_rating: float
    referring_agent_reviews_count: int
    categories: List[str]
    followed_platforms: List[str]
    is_scratched: bool
    is_50_unlocked: bool
    digital_campaign_price: int
    prof_campaign_price: int
    google_review_url: str
    registration_url: str


class AdminCampaignSettingsRequest(BaseModel):
    status: Optional[str] = "live"
    digital_regular_price: Optional[int] = 1999
    digital_campaign_price: Optional[int] = 999
    digital_renewal_price: Optional[int] = 1999
    prof_regular_price: Optional[int] = 9999
    prof_campaign_price: Optional[int] = 4999
    prof_renewal_price: Optional[int] = 9999
    min_profile_percent: Optional[int] = 80
    min_reviews: Optional[int] = 10
    google_review_url: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None


class AdminFinancialLiabilityResponse(BaseModel):
    success: bool = True
    campaign_name: str
    gross_revenue: float
    refund_amount: float
    net_revenue: float
    digital_paid_count: int
    prof_paid_count: int
    potential_liability: float
    current_liability: float
    rewards_issued: float
    health_status: str
    health_color: str
    total_participants: int
    total_qualifying: int
    fraud_flags_count: int
