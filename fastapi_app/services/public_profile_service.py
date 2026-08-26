from fastapi import HTTPException
import json
from fastapi_app.repositories.agent_repository import AgentRepository
from fastapi_app.schemas.public_profile import (
    PublicProfileResponse, BadgeSchema, SocialLinksSchema, 
    InsuranceSegmentSchema, TimelineSchema, 
    PerformanceStatsSchema, ServiceFeeSchema, ReviewSchema
)
import math

class PublicProfileService:
    def __init__(self, agent_repo: AgentRepository):
        self.agent_repo = agent_repo

    def _format_claims_processed(self, claims: float) -> str:
        if claims >= 10000000:
            return f"{(claims / 10000000):.1f} Cr"
        elif claims >= 100000:
            return f"{(claims / 100000):.1f} L"
        elif claims > 0:
            return f"{int(claims):,}"
        else:
            return "0"
            
    def _format_claims_settled(self, claims: float) -> str:
        if claims >= 10000000:
            return f"₹{(claims / 10000000):.1f} Cr"
        elif claims >= 100000:
            return f"₹{(claims / 100000):.1f} L"
        elif claims > 0:
            return f"₹{int(claims):,}"
        else:
            return "—"

    def get_public_profile(self, slug: str) -> PublicProfileResponse:
        agent = self.agent_repo.get_agent_public_profile(slug)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent Profile Not found")
            
        # Security: Return 404 for non-active agents
        active_statuses = ['approved', 'active']
        if agent.status not in active_statuses:
            raise HTTPException(status_code=404, detail="Agent Profile Not found")
            
        profile = agent.profile

        # The endpoint is unauthenticated, so the agent's own visibility switch
        # is the only thing standing between a hidden profile and the public.
        if profile is not None and not profile.is_profile_visible:
            raise HTTPException(status_code=404, detail="Agent Profile Not found")

        show_certificates = profile.show_certificates if profile else True
        show_achievements = profile.show_achievements if profile else True
        show_reviews = profile.show_reviews if profile else True
        perf = agent.performance_stats
        prefs = agent.lead_preferences
        
        display_name = profile.display_name if profile and profile.display_name else agent.fullname
        display_name = display_name.strip() if display_name else "Agent"
        agent_initial = display_name[0].upper() if display_name else "A"
        
        # Badges
        badges = []
        if agent.badge and agent.badge != 'none':
            raw_badges = [b.strip() for b in str(agent.badge).split(',')]
            badge_map = {
                'verified': {'key': 'verified', 'label': 'Verified'},
                'irdai': {'key': 'irdai', 'label': 'Licensed'},
                'trusted': {'key': 'trusted', 'label': 'Trusted'}
            }
            for b in raw_badges:
                key = b.lower()
                if key in badge_map:
                    badges.append(BadgeSchema(**badge_map[key]))
                else:
                    badges.append(BadgeSchema(key=key, label=key.capitalize()))
                    
        # Social links
        social_links = {}
        if profile and profile.social_links:
            try:
                if isinstance(profile.social_links, str):
                    social_links = json.loads(profile.social_links)
                else:
                    social_links = profile.social_links
            except:
                pass
                
        # Insurance Segments priority logic
        segment_values = []
        if agent.insurance_segments:
            segment_values = [s.segment_type.strip().lower() for s in agent.insurance_segments if s.segment_type and s.segment_type != '-']
            segment_values = list(dict.fromkeys(segment_values)) # unique
            
        priority_order = ['health', 'life', 'motor', 'sme']
        ordered_segments = []
        for p in priority_order:
            if p in segment_values:
                ordered_segments.append(p)
        for s in segment_values:
            if s not in ordered_segments:
                ordered_segments.append(s)
                
        insurance_segments = []
        for s in ordered_segments:
            label = 'SME' if s == 'sme' else s.capitalize()
            insurance_segments.append(InsuranceSegmentSchema(key=s, label=label))
            
        # Reviews & Rating calculation
        approved_reviews = [r for r in agent.reviews if r.is_approved] if agent.reviews else []
        review_count = len(approved_reviews)
        average_rating_val = sum(r.rating for r in approved_reviews) / review_count if review_count > 0 else 0.0
        average_rating_str = f"{average_rating_val:.1f}"
        
        # Career Timelines formatting
        timelines = agent.career_timelines or []
        timelines = sorted(timelines, key=lambda x: x.year or 0, reverse=True)
        
        career_timeline = []
        certifications = []
        achievements = []
        
        has_pos_license = profile.has_pos_license if profile else False
        has_license_number = bool(profile.license_number) if profile else False
        
        if has_license_number:
            certifications.append(f"IRDAI Certified Agent (License: {profile.license_number})")
            
        for t in timelines:
            event_type = t.event_type.strip().lower() if t.event_type else ""
            year_month = f"{t.month or ''} {t.year or ''}".strip()
            
            if event_type == 'certification':
                cert_str = t.event_text or ""
                if year_month:
                    cert_str += f" ({year_month})"
                certifications.append(cert_str)
            elif event_type in ['achievement', 'award', 'milestone']:
                achievements.append(t.event_text or "")
            else:
                career_timeline.append(TimelineSchema(
                    year_month=year_month,
                    text=t.event_text or ""
                ))
                
        if not achievements and profile and profile.career_highlights:
            achievements.append(profile.career_highlights)
            
        def safe_float(val):
            if not val:
                return 0.0
            try:
                clean_val = str(val).replace('%', '').replace('₹', '').replace(',', '').strip()
                return float(clean_val)
            except ValueError:
                return 0.0

        # Performance Stats
        cp = safe_float(perf.claims_processed) if perf else 0.0
        ca = safe_float(perf.claims_amount) if perf else 0.0
        perf_schema = PerformanceStatsSchema(
            clients_served=str(agent.client_base or '0'),
            claims_processed=self._format_claims_processed(cp),
            success_rate=str(perf.success_rate or '98') if perf else '98',
            claims_settled=self._format_claims_settled(ca),
            response_time=f"< {perf.response_time or '2'} hours" if perf else "< 2 hours"
        )
        
        # Service Fees
        service_fees = [ServiceFeeSchema(label="New Policy", value="Free")]
        if prefs and prefs.leads_claims_support:
            claim_fee = "Free"
            if prefs.claims_charging == 'fee':
                claim_fee = f"₹{prefs.claims_fee_amount}"
            elif prefs.claims_charging == 'percentage':
                claim_fee = f"{prefs.claims_percent}%"
            service_fees.append(ServiceFeeSchema(label="Claim Help", value=claim_fee))
            
        if prefs and prefs.leads_portfolio_analysis:
            audit_fee = "Free"
            if prefs.portfolio_charging != 'free':
                audit_fee = f"₹{prefs.portfolio_fee}"
            service_fees.append(ServiceFeeSchema(label="Review", value=audit_fee))
            
        from apps.agents.models import resolve_stored_file_url

        def get_media_url(path: str) -> str:
            return resolve_stored_file_url(
                path,
                fallback_subdirs=(
                    'app/public/profile',
                    'agent/profiles',
                    'app/public/achievement',
                    'agent/achievements',
                ),
                missing='',
            )

        # Media
        media_urls = []
        if agent.achievement_photos:
            media_urls = [
                get_media_url(p.photo_path)
                for p in agent.achievement_photos
                if p.photo_path
            ]
            media_urls = [url for url in media_urls if url]
            
        # Reviews Mapping
        review_schemas = []
        for r in sorted(approved_reviews, key=lambda x: x.created_at, reverse=True):
            r_name = r.user.fullname if r.user else r.reviewer_name
            r_name = r_name or 'User'
            review_schemas.append(ReviewSchema(
                reviewer_name=r_name,
                reviewer_initial=r_name[0].upper(),
                rating=r.rating or 5,
                text=r.review or "",
                date=r.created_at.strftime('%b %d, %Y') if r.created_at else "N/A"
            ))

        return PublicProfileResponse(
            agent_id=agent.id,
            display_name=display_name,
            agent_initial=agent_initial,
            profile_photo_url=get_media_url(profile.profile_photo_path) if profile else None,
            badges=badges,
            career_highlights=profile.career_highlights if (profile and profile.career_highlights) else "Experienced insurance professional with a proven track record of helping clients find the right coverage.",
            experience_years=f"{agent.experience_range or '0'} years",
            client_base=f"{agent.client_base or '0+'} clients",
            languages=profile.languages if profile and profile.languages else "English, Hindi",
            insurance_segments=insurance_segments,
            average_rating=average_rating_str,
            review_count=review_count,
            social_links=SocialLinksSchema(
                linkedin=social_links.get('linkedin_url', social_links.get('linkedin')),
                facebook=social_links.get('facebook_url', social_links.get('facebook')),
                instagram=social_links.get('instagram_url', social_links.get('instagram')),
                youtube=social_links.get('youtube_url', social_links.get('youtube')),
                google_business=social_links.get('google_business')
            ),
            career_timeline=career_timeline,
            certifications=certifications,
            achievements=achievements,
            performance_stats=perf_schema,
            service_fees=service_fees,
            media_urls=media_urls,
            reviews=review_schemas
        )
