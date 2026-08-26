import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.models.agent_subscription import AgentSubscription
from fastapi_app.models.agent_insurance_segment import AgentInsuranceSegment
from fastapi_app.models.referral_code import ReferralCode

from fastapi_app.repositories.agent_lead_repository import AgentLeadRepository
from fastapi_app.repositories.agent_profile_view_repository import AgentProfileViewRepository
from fastapi_app.repositories.agent_portfolio_repository import AgentPortfolioRepository
from fastapi_app.repositories.agent_lead_preference_repository import AgentLeadPreferenceRepository
from fastapi_app.repositories.agent_serviceable_city_repository import AgentServiceableCityRepository
from fastapi_app.repositories.referral_code_repository import ReferralCodeRepository
from fastapi_app.repositories.site_setting_repository import SiteSettingRepository

from fastapi_app.schemas.dashboard import (
    AgentSummary, SubscriptionInfo, TrialInfo,
    LeadStats, PerformanceOverview, RecentLead,
    ProfileCompletion, ReferralInfo, TierInfo, DashboardResponse
)

logger = logging.getLogger(__name__)

class DashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.lead_repo = AgentLeadRepository(db)
        self.view_repo = AgentProfileViewRepository(db)
        self.portfolio_repo = AgentPortfolioRepository(db)
        self.lead_pref_repo = AgentLeadPreferenceRepository(db)
        self.city_repo = AgentServiceableCityRepository(db)
        self.referral_repo = ReferralCodeRepository(db)
        self.setting_repo = SiteSettingRepository(db)

    def get_dashboard(self, agent: Agent) -> DashboardResponse:
        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        profile: Optional[AgentProfile] = self.db.query(AgentProfile).filter(
            AgentProfile.agent_id == agent.id
        ).first()

        active_subscription: Optional[AgentSubscription] = self.db.query(AgentSubscription).filter(
            AgentSubscription.agent_id == agent.id,
            AgentSubscription.status == "active",
            AgentSubscription.expires_at > datetime.utcnow()
        ).first()

        insurance_segments = self.db.query(AgentInsuranceSegment).filter(
            AgentInsuranceSegment.agent_id == agent.id
        ).all()

        cities = self.city_repo.get_cities_for_agent(agent.id)
        city_count = len(cities)
        city_names = [c.name for c in cities]

        segment_types = self._get_segment_types(insurance_segments)

        try:
            total_leads = self.lead_repo.count_total(agent.id)
            monthly_leads = self.lead_repo.count_monthly(agent.id, start_of_month.replace(tzinfo=None))
            new_leads = self.lead_repo.count_by_status(agent.id, "new")
            contacted_leads = self.lead_repo.count_by_status(agent.id, "contacted")
            follow_up_leads = self.lead_repo.count_by_status(agent.id, "follow_up")
            closed_leads = self.lead_repo.count_by_status(agent.id, "closed")
        except Exception as e:
            logger.warning(f"Dashboard lead stats unavailable for agent #{agent.id}: {e}")
            total_leads = monthly_leads = new_leads = contacted_leads = follow_up_leads = closed_leads = 0

        active_leads = new_leads + contacted_leads + follow_up_leads
        conversion_rate = round((closed_leads / total_leads) * 100, 1) if total_leads > 0 else 0.0

        try:
            total_page_views = self.view_repo.sum_total_views(agent.id)
            monthly_visits = self.view_repo.sum_monthly_views(agent.id, start_of_month.date())
        except Exception as e:
            logger.warning(f"Dashboard profile view stats unavailable for agent #{agent.id}: {e}")
            total_page_views = monthly_visits = 0

        try:
            recent_leads_rows = self.lead_repo.get_recent(agent.id, 10)
        except Exception as e:
            logger.warning(f"Dashboard recent leads unavailable for agent #{agent.id}: {e}")
            recent_leads_rows = []

        profile_completion = self._calculate_completion(
            agent=agent,
            profile=profile,
            city_count=city_count,
            segment_count=len(insurance_segments),
        )

        subscription_info = self._build_subscription(active_subscription)
        trial_info = self._build_trial_info(agent, active_subscription)
        referral_info = self._build_referral_info(agent)

        return DashboardResponse(
            success=True,
            agent=self._build_agent_summary(agent, profile),
            subscription=subscription_info,
            trial=trial_info,
            performance=PerformanceOverview(
                conversion_rate=conversion_rate,
                monthly_target=0,
                total_page_views=total_page_views,
                contact_requests=total_leads,
                monthly_visits=monthly_visits,
            ),
            lead_stats=LeadStats(
                total_leads=total_leads,
                monthly_leads=monthly_leads,
                new_leads=new_leads,
                contacted_leads=contacted_leads,
                follow_up_leads=follow_up_leads,
                closed_leads=closed_leads,
                active_leads=active_leads,
                conversion_rate=conversion_rate,
            ),
            recent_leads=[self._map_lead(lead) for lead in recent_leads_rows],
            profile_completion=profile_completion,
            insurance_segments=segment_types,
            serviceable_cities=city_names,
            referral=referral_info,
        )

    @staticmethod
    def _resolve_photo_url(path: str) -> Optional[str]:
        try:
            from apps.agents.models import resolve_stored_file_url

            return resolve_stored_file_url(
                path,
                fallback_subdirs=('app/public/profile', 'agent/profiles'),
                missing='',
            ) or None
        except Exception as e:
            logger.warning("Could not resolve profile photo path %r: %s", path, e)
            return path

    def _build_agent_summary(self, agent: Agent, profile: Optional[AgentProfile]) -> AgentSummary:
        display_name = None
        photo_url = None
        slug = None
        languages = None
        agency_name = None

        if profile:
            display_name = profile.display_name
            slug = profile.slug
            languages = profile.languages
            agency_name = profile.agency_name
            if profile.profile_photo_path:
                # Stored paths are relative (or legacy Laravel paths). Resolve
                # them the same way GET /profile does so clients get one shape.
                photo_url = self._resolve_photo_url(profile.profile_photo_path)

        return AgentSummary(
            id=agent.id,
            fullname=agent.fullname,
            display_name=display_name or agent.fullname,
            email=agent.email,
            mobile=agent.mobile,
            status=str(agent.status),
            plan_type=agent.plan_type,
            photo_url=photo_url,
            profile_slug=slug,
            experience_range=agent.experience_range,
            languages=languages,
            agency_name=agency_name,
        )

    def _build_subscription(self, sub: Optional[AgentSubscription]) -> SubscriptionInfo:
        if not sub:
            return SubscriptionInfo(is_active=False)

        raw_plan = sub.selected_plan or "Free Plan"
        try:
            decoded = json.loads(raw_plan)
            plan_name = decoded.get("name", raw_plan) if isinstance(decoded, dict) else raw_plan
        except (json.JSONDecodeError, TypeError):
            plan_name = raw_plan.replace("_", " ").replace("-", " ").title()

        return SubscriptionInfo(
            plan_name=plan_name,
            plan_type=sub.selected_plan,
            status=sub.status,
            expires_at=sub.expires_at,
            is_active=True,
        )

    def _build_trial_info(self, agent: Agent, sub: Optional[AgentSubscription]) -> TrialInfo:
        is_on_trial = (
            agent.plan_type == "free_trial"
            and agent.trial_ends_at is not None
            and agent.trial_ends_at > datetime.utcnow()
        )
        trial_expired = (
            agent.plan_type == "free_trial"
            and agent.trial_ends_at is not None
            and agent.trial_ends_at <= datetime.utcnow()
        )

        days_left = None
        if is_on_trial and agent.trial_ends_at:
            delta = agent.trial_ends_at - datetime.utcnow()
            days_left = max(0, delta.days)

        discount_pct = 0
        starter_full = 2359
        prof_full = 8258

        if is_on_trial:
            admin_default = int(
                self.setting_repo.get_json_value("trial_upgrade_discount", 20) or 20
            )
            agent_specific = int(agent.upgrade_discount_percent or 0)

            referral_discount = 0
            ref_code = self.referral_repo.get_by_agent(agent.id)
            if ref_code:
                tier = ref_code.current_tier()
                if tier:
                    referral_discount = tier.get("discount", 0)

            discount_pct = max(admin_default, agent_specific, referral_discount)

            pricing_config = self.setting_repo.get_json_value("pricing_config", {})
            if pricing_config:
                starter_full = pricing_config.get("starter", {}).get("full_price", 2359)
                prof_full = pricing_config.get("professional", {}).get("full_price", 8258)

            if getattr(agent, "referral_reward_type", None) == "pro_plan_1rs":
                prof_full_discounted = 1
                discount_pct_display = 9999
            else:
                prof_full_discounted = round(prof_full * (100 - discount_pct) / 100)
                discount_pct_display = discount_pct

            starter_discounted = round(starter_full * (100 - discount_pct) / 100)
        else:
            starter_discounted = starter_full
            prof_full_discounted = prof_full
            discount_pct_display = 0

        return TrialInfo(
            is_on_trial=is_on_trial,
            trial_days_left=days_left,
            trial_expired=trial_expired,
            upgrade_discount_pct=discount_pct_display if is_on_trial else 0,
            starter_full_price=starter_full,
            starter_discounted_price=starter_discounted,
            professional_full_price=prof_full,
            professional_discounted_price=prof_full_discounted,
        )

    def _calculate_completion(
        self,
        agent: Agent,
        profile: Optional[AgentProfile],
        city_count: int,
        segment_count: int,
    ) -> ProfileCompletion:
        completion = 15

        has_address_and_languages = False
        has_serviceable_cities = False
        has_insurance_segments = False
        has_portfolio = False
        has_profile_photo = False
        has_lead_preferences = False

        if profile:
            if profile.address and profile.languages:
                completion += 15
                has_address_and_languages = True

            has_service_pincode = bool(
                profile.service_pincodes
                and json.loads(profile.service_pincodes) if isinstance(profile.service_pincodes, str)
                else profile.service_pincodes
            )
            if has_service_pincode and city_count > 0:
                completion += 15
                has_serviceable_cities = True

            if segment_count > 0:
                completion += 15
                has_insurance_segments = True

            portfolio_count = self.portfolio_repo.count_by_agent(agent.id)
            if portfolio_count > 0:
                completion += 15
                has_portfolio = True

            if profile.profile_photo_path:
                completion += 10
                has_profile_photo = True

            if self.lead_pref_repo.exists_for_agent(agent.id):
                completion += 15
                has_lead_preferences = True

        if str(agent.status) == "pending":
            completion = 100

        completion = min(completion, 100)

        return ProfileCompletion(
            percentage=completion,
            has_address_and_languages=has_address_and_languages,
            has_serviceable_cities=has_serviceable_cities,
            has_insurance_segments=has_insurance_segments,
            has_portfolio=has_portfolio,
            has_profile_photo=has_profile_photo,
            has_lead_preferences=has_lead_preferences,
        )

    def _build_referral_info(self, agent: Agent) -> ReferralInfo:
        referral_config = self.setting_repo.get_json_value(
            "referral_config", {"eligibility": "free_trial_only"}
        )
        eligibility = referral_config.get("eligibility", "free_trial_only") if referral_config else "free_trial_only"
        show_referral = (eligibility == "all" or agent.plan_type == "free_trial")

        if not show_referral:
            return ReferralInfo(show_referral=False)

        ref_code: Optional[ReferralCode] = self.referral_repo.get_by_agent(agent.id)
        if not ref_code:
            return ReferralInfo(show_referral=True)

        current_tier_data = ref_code.current_tier()
        next_tier_data = ref_code.next_tier()

        return ReferralInfo(
            show_referral=True,
            referral_code=ref_code.code,
            total_referrals=ref_code.total_referrals,
            current_tier=TierInfo(**current_tier_data) if current_tier_data else None,
            next_tier=TierInfo(**next_tier_data) if next_tier_data else None,
        )

    def _get_segment_types(self, insurance_segments) -> list:
        priority = ["health", "life", "motor", "sme"]
        raw = [str(s.segment_type).lower().strip() for s in insurance_segments if s.segment_type]
        unique = list(dict.fromkeys(raw))
        ordered = [p for p in priority if p in unique]
        ordered += [s for s in unique if s not in ordered]
        return ordered

    def _map_lead(self, lead) -> RecentLead:
        return RecentLead(
            id=lead.id,
            customer_name=lead.customer_name,
            customer_mobile=lead.customer_mobile,
            customer_email=lead.customer_email,
            customer_pincode=lead.customer_pincode,
            enquiry_requirements=lead.enquiry_requirements,
            interaction_type=lead.interaction_type,
            lead_status=lead.lead_status,
            created_at=lead.created_at,
        )
