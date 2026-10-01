import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from fastapi_app.models.agent import Agent
from fastapi_app.models.subscription_plan import SubscriptionPlan
from fastapi_app.models.agent_subscription import AgentSubscription
from fastapi_app.models.site_setting import SiteSetting
from fastapi_app.models.referral_code import ReferralCode
from fastapi_app.services.plan_pricing import (
    MOBILE_PLAN_SLUGS,
    allowed_platforms,
    get_or_create_offer,
    load_offer,
    load_pricing_config,
    offer_state,
    quote_plan,
)
from fastapi_app.schemas.plans import (
    PlanFeatureItem,
    PlanPricingDetails,
    PlanItemSchema,
    AgentCurrentPlanInfo,
    UpgradeDiscountInfo,
    PlansListResponse,
)

logger = logging.getLogger(__name__)

# Canonical feature mapping for plans
PLAN_FEATURE_DEFINITIONS = [
    ("show_profile_section", "Public Profile Customization"),
    ("is_listed_in_directory", "Listed in Find Agents Directory"),
    ("show_performance_stats", "Performance Overview & Analytics"),
    ("show_sales_insights", "Sales Insights & Recommendations"),
    ("show_new_business_leads", "New Business Lead Enquiries"),
    ("show_recent_leads", "Lead Management & Follow-ups"),
    ("show_agent_certificate", "Verified IRDAI / AMFI Badge"),
    ("show_career_timeline", "Career Timeline & Milestones"),
    ("show_professional_bio", "Professional Bio & AI Bio Generator"),
    ("show_portfolio", "Insurance Products Portfolio"),
    ("show_claim_support", "Claims Support Showcase"),
    ("show_companies", "Partner Insurance Companies Display"),
    ("show_achievement", "Gallery & Achievement Photos"),
    ("show_review_management", "Customer Reviews & Ratings"),
    ("show_rank_boost_tips", "Profile Rank Boost Tips"),
    ("premium_priority_support", "Priority Support & Assistance"),
]

SLUG_NORMALISE = {
    'basic': 'starter',
    'starter': 'starter',
    'standard': 'starter',
    'starters_plan': 'starter',
    'starters-plan': 'starter',
    'free trial': 'free_trial',
    'free_trial': 'free_trial',
    'professional': 'professional',
    'professionals_plan': 'professional',
    'professionals-plan': 'professional',
    'pro': 'professional',
    'exclusive': 'exclusive',
    'exclusive_partner': 'exclusive',
    'exclusive_partner_plan': 'exclusive',
    'elite': 'starter',
}


def normalize_plan_slug(plan_type: Optional[str]) -> str:
    if not plan_type:
        return ""
    pt = str(plan_type).strip().lower().replace(" ", "_")
    return SLUG_NORMALISE.get(pt, pt)




def _website_total(full_price: float, discount_pct: int) -> float:
    """GST-inclusive total exactly as the website upgrade computes it."""
    final = round(float(full_price) * (100 - discount_pct) / 100)
    base = round(final / 1.18, 0)
    return float(base + round(base * 0.18, 0))


class PlanService:
    def __init__(self, db: Session):
        self.db = db

    def get_plans_list(self, agent: Optional[Agent] = None) -> PlansListResponse:
        """
        Two app plans, priced from the admin choose-plan settings.

        List price is the admin full price (1999 / 9999) until this agent
        scratches. After a scratch, the admin scratch price applies, and any
        recorded social follows move the price to the admin follow tier.
        """
        db_plans = self.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.is_active == True
        ).all()
        by_slug = {}
        for plan in db_plans:
            slug = normalize_plan_slug(getattr(plan, 'slug', '') or getattr(plan, 'name', ''))
            if slug in MOBILE_PLAN_SLUGS and slug not in by_slug:
                by_slug[slug] = plan
        fallback = {plan.slug: plan for plan in self._get_fallback_plans()}

        agent_current_plan = None
        upgrade_discount = None
        agent_current_slug = ""
        is_pro_1rs = False
        if agent:
            agent_current_slug = normalize_plan_slug(agent.plan_type)
            agent_current_plan = self._resolve_current_agent_plan(agent)
            upgrade_discount, _, is_pro_1rs = self._resolve_upgrade_discount(
                agent,
                is_on_trial=bool(agent_current_plan and agent_current_plan.is_on_trial),
            )

        config = load_pricing_config(self.db)
        offer = load_offer(self.db, agent)
        scratched, followed = offer_state(offer)
        follow_count = len(followed)

        plan_items: List[PlanItemSchema] = []
        for index, slug in enumerate(MOBILE_PLAN_SLUGS, start=1):
            quote = quote_plan(
                config,
                slug,
                scratched=slug in scratched,
                follow_count=follow_count,
                force_rupee=bool(is_pro_1rs and slug == "professional"),
            )
            source = by_slug.get(slug) or fallback[slug]
            pricing_details = PlanPricingDetails(
                actual_price=quote["full_price"],
                discounted_price=quote["display_price"],
                agent_discount_pct=quote["discount_pct"],
                base_price_exclusive_gst=quote["payable_base"],
                gst_rate_percent=18.0,
                gst_amount=quote["gst_amount"],
                final_price_inclusive_gst=quote["payable_total"],
                formatted_final_price=f"₹{int(quote['display_price']):,}",
                display_price=quote["display_price"],
                price_after_scratch=quote["price_after_scratch"],
                scratch_enabled=quote["scratch_enabled"],
                scratch_revealed=quote["scratch_revealed"],
                scratch_price=quote["scratch_price"],
                follow_count=quote["follow_count"],
                follow_discount=quote["follow_discount"],
            )
            plan_items.append(
                PlanItemSchema(
                    id=getattr(source, 'id', index) or index,
                    name=quote["name"],
                    slug=slug,
                    description=quote["description"] or (getattr(source, 'description', '') or ""),
                    color_theme=getattr(source, 'color_theme', None) or "starter-theme",
                    badge_text=quote["badge"] or getattr(source, 'badge_text', None),
                    sort_order=index,
                    is_current_plan=bool(agent and agent_current_slug and slug == agent_current_slug),
                    pricing=pricing_details,
                    features=self._extract_plan_features(source),
                )
            )

        links = []
        for link in config.get("social_links") or []:
            if isinstance(link, dict) and link.get("platform"):
                links.append({
                    "platform": str(link.get("platform")),
                    "url": str(link.get("url") or ""),
                })

        return PlansListResponse(
            success=True,
            agent_current_plan=agent_current_plan,
            upgrade_discount=upgrade_discount,
            social_discount_active=bool(config.get("social_discount_active", True)),
            followed_platforms=followed,
            social_links=links,
            plans=plan_items,
        )

    def record_scratch(self, agent: Agent, plan_slug: str) -> PlansListResponse:
        slug = normalize_plan_slug(plan_slug)
        if slug not in MOBILE_PLAN_SLUGS:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Choose Starter or Professional to scratch.")
        offer = get_or_create_offer(self.db, agent)
        if slug == "starter":
            offer.scratched_starter = True
        else:
            offer.scratched_professional = True
        self.db.add(offer)
        self.db.commit()
        return self.get_plans_list(agent)

    def record_follow(self, agent: Agent, platform: str) -> PlansListResponse:
        config = load_pricing_config(self.db)
        name = str(platform or "").strip().lower()
        if name not in allowed_platforms(config):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Unknown platform.")
        offer = get_or_create_offer(self.db, agent)
        followed = list(offer.followed_platforms or [])
        normalized = [str(item).strip().lower() for item in followed]
        if name not in normalized:
            normalized.append(name)
            offer.followed_platforms = normalized
            self.db.add(offer)
            self.db.commit()
        return self.get_plans_list(agent)

    def _resolve_current_agent_plan(self, agent: Agent) -> AgentCurrentPlanInfo:
        """Resolve agent's current active plan status, trial state, and expiry."""
        sub = self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent.id,
            AgentSubscription.status == "active"
        ).order_by(AgentSubscription.created_at.desc()).first()

        plan_name = getattr(sub, 'selected_plan', None) or agent.plan_type or "Free Trial"
        status = getattr(sub, 'status', None) or agent.status or "active"
        expires_at = getattr(sub, 'expires_at', None)

        now = datetime.now()  # DB datetimes are naive IST (USE_TZ=False)
        is_on_trial = bool(
            agent.plan_type == "free_trial"
            and agent.trial_ends_at is not None
            and agent.trial_ends_at > now
        )

        trial_days_left = None
        if is_on_trial and agent.trial_ends_at:
            trial_days_left = max(0, (agent.trial_ends_at - now).days)

        return AgentCurrentPlanInfo(
            plan_type=agent.plan_type,
            plan_name=plan_name.title() if plan_name else "Free Trial",
            status=status,
            is_active=bool(status in ["active", "approved"]),
            is_on_trial=is_on_trial,
            trial_days_left=trial_days_left,
            trial_ends_at=agent.trial_ends_at,
            expires_at=expires_at,
        )

    def _pricing_config(self) -> Dict[str, Any]:
        setting = self.db.query(SiteSetting).filter(SiteSetting.key == "pricing_config").first()
        if not setting or not setting.value:
            return {}
        try:
            import json
            value = json.loads(setting.value)
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    def _resolve_upgrade_discount(self, agent: Agent, is_on_trial: bool = False) -> tuple[UpgradeDiscountInfo, int, bool]:
        """Compute special upgrade discount available for the agent.

        Like the website, the percentage discount applies only during a free
        trial; the Professional @ Rs 1 referral reward applies regardless.
        """
        # 1. Admin default trial upgrade discount
        admin_setting = self.db.query(SiteSetting).filter(SiteSetting.key == "trial_upgrade_discount").first()
        admin_default = 20
        if admin_setting and admin_setting.value:
            try:
                admin_default = int(admin_setting.value)
            except Exception:
                pass

        # 2. Agent-specific discount
        agent_specific = int(agent.upgrade_discount_percent or 0)

        # 3. Referral tier discount
        referral_discount = 0
        ref_code = self.db.query(ReferralCode).filter(ReferralCode.agent_id == agent.id).first()
        if ref_code:
            try:
                tier = ref_code.current_tier()
                if tier and isinstance(tier, dict):
                    referral_discount = int(tier.get("discount", 0) or 0)
            except Exception:
                pass

        # Maximum available discount (free-trial agents only, as on the website)
        applicable_discount = max(admin_default, agent_specific, referral_discount) if is_on_trial else 0

        is_pro_1rs = getattr(agent, "referral_reward_type", None) == "pro_plan_1rs"
        offer_msg = None
        if is_pro_1rs:
            offer_msg = "Special Reward: Professional's Plan unlocked for ₹1 only!"
        elif applicable_discount > 0:
            offer_msg = f"Special {applicable_discount}% discount applied on plan upgrades!"

        discount_info = UpgradeDiscountInfo(
            applicable_discount_pct=99 if is_pro_1rs else applicable_discount,
            trial_discount_pct=admin_default,
            agent_specific_discount_pct=agent_specific,
            referral_discount_pct=referral_discount,
            referral_reward_type=agent.referral_reward_type,
            offer_message=offer_msg,
        )

        return discount_info, applicable_discount, is_pro_1rs

    def _extract_plan_features(self, plan: Any) -> List[PlanFeatureItem]:
        """Extract all feature toggles with human-readable labels."""
        features = []
        for attr, label in PLAN_FEATURE_DEFINITIONS:
            is_enabled = bool(getattr(plan, attr, True))
            features.append(
                PlanFeatureItem(
                    key=attr,
                    label=label,
                    is_enabled=is_enabled,
                )
            )
        return features

    def _get_fallback_plans(self) -> List[Any]:
        """In-memory fallback plans if database table has not been populated."""
        class MockPlan:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        return [
            MockPlan(
                id=1,
                name="Starter's Plan",
                slug="starter",
                description="Essential digital presence and local verification for insurance advisors.",
                color_theme="starter-theme",
                badge_text="Most Popular",
                sort_order=1,
                actual_price=2359.00,
                discounted_price=999.00,
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
                premium_priority_support=False,
            ),
            MockPlan(
                id=2,
                name="Professional's Plan",
                slug="professional",
                description="Advanced visibility, top rank priority, SEO, and full client lead management.",
                color_theme="pro-theme",
                badge_text="Recommended",
                sort_order=2,
                actual_price=8258.00,
                discounted_price=4999.00,
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
                premium_priority_support=True,
            ),
        ]
