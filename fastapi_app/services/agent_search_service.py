import os
import sys
import logging
from typing import List, Tuple, Any, Dict
import re

logger = logging.getLogger(__name__)

# Ensure Django environment is configured before importing Django models
src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
from django.apps import apps
if not apps.ready:
    django.setup()

from django.db.models import Q, Value, FloatField
from django.db.models.expressions import RawSQL
from apps.agents.models import Agent
from apps.home.services.distance import DistanceService
from apps.home.services.geocoding import GeocodingService

from fastapi_app.schemas.agent_search import (
    FindAgentsRequest,
    FindAgentsResponse,
    AgentCardSchema,
    RecognitionBadge,
    PaginationMeta
)


class MockGET:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=''):
        val = self._data.get(key)
        if isinstance(val, list):
            return str(val[0]) if val else default
        return str(val) if val is not None else default

    def getlist(self, key):
        val = self._data.get(key)
        if isinstance(val, list):
            return [str(x) for x in val if x is not None]
        elif val is not None and str(val).strip() != '':
            return [str(val)]
        return []

    def __contains__(self, item):
        val = self._data.get(item)
        if isinstance(val, list):
            return bool(val)
        return val is not None and str(val).strip() != ''


class MockRequest:
    def __init__(self, get_data: dict, session_data: dict = None):
        self.GET = MockGET(get_data)
        self.session = session_data if session_data is not None else {}
        self.headers = {}
        self.path = '/api/v1/find-agents'


class AgentSearchService:
    @staticmethod
    def _build_agent_queryset(req: FindAgentsRequest):
        # Base query
        query = Agent.objects.filter(status='active').exclude(profile__is_card_visible=False)
        query = query.select_related('profile', 'performanceStats').prefetch_related(
            'insuranceSegments', 'reviews', 'serviceableCities', 'productExpertise'
        )

        user_lat = req.lat
        user_lng = req.lng
        invalid_pincode = False
        
        # Pincode Resolution
        if not user_lat and not user_lng and req.pincode:
            if not re.match(r'^[1-9]\d{5}$', req.pincode):
                invalid_pincode = True
            else:
                try:
                    geo_svc = GeocodingService()
                    coords = geo_svc.resolve_coordinates(req.pincode)
                    if coords:
                        user_lat = coords['lat']
                        user_lng = coords['lng']
                    else:
                        invalid_pincode = True
                except Exception:
                    coords = DistanceService.get_pincode_coordinates(req.pincode)
                    if coords:
                        user_lat = coords['lat']
                        user_lng = coords['lng']
                    else:
                        invalid_pincode = True

        if invalid_pincode:
            return query.none(), user_lat, user_lng, invalid_pincode

        from apps.home.services.agent_filters import (
            apply_insurance_product_filter,
            apply_insurance_type_filter,
            apply_location_text_filter,
        )

        query, db_types = apply_insurance_type_filter(query, req.insurance_types)

        if req.service_types:
            q_pref = Q()
            if any(s in ['New Policy', 'Buying new insurance'] for s in req.service_types):
                q_pref |= Q(leadPreferences__leads_new_business=True)
            if any(s in ['Claim Assistance', 'Claim'] for s in req.service_types):
                q_pref |= Q(leadPreferences__leads_claims_support=True)
            if any(s in ['Policy Review', 'Insurance audit', 'Port / transfer'] for s in req.service_types):
                q_pref |= Q(leadPreferences__leads_portfolio_analysis=True)
                
            q_spec = Q()
            if db_types:
                q_spec = Q(insuranceSegments__segment_type__in=db_types)
                
            q_no_pref = Q(leadPreferences__isnull=True)
            query = query.filter(q_pref | q_spec | q_no_pref).distinct()

        query = apply_location_text_filter(
            query, req.location, pincode=req.pincode, has_coords=bool(user_lat and user_lng)
        )
        query = apply_insurance_product_filter(query, req.insurance_companies, db_types)

        if req.claim_insurance_company:
            query = query.filter(
                Q(portfolios__primary_companies__icontains=req.claim_insurance_company) |
                Q(portfolios__secondary_companies__icontains=req.claim_insurance_company)
            ).distinct()

        if req.search:
            query = query.filter(
                Q(fullname__icontains=req.search) |
                Q(profile__city__icontains=req.search) |
                Q(profile__state__icontains=req.search)
            ).distinct()

        if db_types:
            placeholders = ", ".join(["%s"] * len(db_types))
            filter_match_sql = f"(SELECT COUNT(*) FROM agent_insurance_segments WHERE agent_insurance_segments.agent_id = agents.id AND agent_insurance_segments.segment_type IN ({placeholders}))"
            filter_match_params = tuple(db_types)
        else:
            filter_match_sql = "(SELECT COUNT(*) FROM agent_insurance_segments WHERE agent_insurance_segments.agent_id = agents.id AND 1=0)"
            filter_match_params = ()

        smart_rank_expr = f"""
            (CASE 
                WHEN CAST(COALESCE(NULLIF(agents.experience_range, ''), NULLIF((SELECT experience_years FROM agent_profiles WHERE agent_profiles.agent_id = agents.id), 0), 0) AS UNSIGNED) >= 15 THEN 20 
                ELSE (CAST(COALESCE(NULLIF(agents.experience_range, ''), NULLIF((SELECT experience_years FROM agent_profiles WHERE agent_profiles.agent_id = agents.id), 0), 0) AS UNSIGNED) / 15) * 20 
            END) +
            (CASE WHEN agents.client_base >= 500 THEN 20 ELSE (IFNULL(agents.client_base, 0) / 500) * 20 END) +
            (CASE 
                WHEN (SELECT IFNULL(claims_processed, 0) FROM agent_performance_stats WHERE agent_performance_stats.agent_id = agents.id) >= 100 THEN 20 
                ELSE (SELECT IFNULL(claims_processed, 0) FROM agent_performance_stats WHERE agent_performance_stats.agent_id = agents.id) / 100 * 20 
            END) +
            (CASE WHEN agents.badge IS NOT NULL AND agents.badge != 'none' AND agents.badge != '' THEN 15 ELSE 0 END) +
            (CASE WHEN (SELECT AVG(rating) FROM agent_reviews WHERE agent_reviews.agent_id = agents.id AND agent_reviews.is_approved = 1) >= 4.5 THEN 10 ELSE 0 END) +
            (CASE 
                WHEN COALESCE(
                    (SELECT last_login_at FROM users WHERE users.id = agents.user_id),
                    (SELECT last_login FROM auth_user WHERE auth_user.id = agents.user_id)
                ) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 DAY) THEN 50
                WHEN COALESCE(
                    (SELECT last_login_at FROM users WHERE users.id = agents.user_id),
                    (SELECT last_login FROM auth_user WHERE auth_user.id = agents.user_id)
                ) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 14 DAY) THEN 25
                WHEN COALESCE(
                    (SELECT last_login_at FROM users WHERE users.id = agents.user_id),
                    (SELECT last_login FROM auth_user WHERE auth_user.id = agents.user_id)
                ) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 30 DAY) THEN 10
                ELSE 0
            END) +
            ((
                (CASE WHEN (SELECT profile_photo_path FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) IS NOT NULL AND (SELECT profile_photo_path FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) != '' THEN 1 ELSE 0 END) +
                (CASE WHEN (SELECT address FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) IS NOT NULL AND (SELECT address FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) != '' THEN 1 ELSE 0 END) +
                (CASE WHEN (agents.experience_range IS NOT NULL AND agents.experience_range != '') OR (SELECT experience_years FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) > 0 THEN 1 ELSE 0 END) +
                (CASE WHEN (SELECT whatsapp FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) IS NOT NULL AND (SELECT whatsapp FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) != '' THEN 1 ELSE 0 END) +
                (CASE WHEN (SELECT license_number FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) IS NOT NULL AND (SELECT license_number FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) != '' THEN 1 ELSE 0 END) +
                (CASE WHEN (SELECT languages FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) IS NOT NULL AND (SELECT languages FROM agent_profiles WHERE agent_profiles.agent_id = agents.id) != '' THEN 1 ELSE 0 END)
            ) * 5) +
            ({filter_match_sql} * 30)
        """

        query = query.annotate(padosi_smart_rank=RawSQL(smart_rank_expr, filter_match_params))

        if user_lat is not None and user_lng is not None:
            dist_sql = "(CASE WHEN agents.latitude IS NOT NULL AND agents.longitude IS NOT NULL THEN (6371 * acos(cos(radians(%s)) * cos(radians(agents.latitude)) * cos(radians(agents.longitude) - radians(%s)) + sin(radians(%s)) * sin(radians(agents.latitude)))) ELSE 999999 END)"
            query = query.annotate(distance_db=RawSQL(dist_sql, (user_lat, user_lng, user_lat)))
            query = query.filter(distance_db__lte=50)
        else:
            query = query.annotate(distance_db=Value(999999.0, output_field=FloatField()))

        exp_sql = "CAST(COALESCE(NULLIF(agents.experience_range, ''), NULLIF((SELECT experience_years FROM agent_profiles WHERE agent_profiles.agent_id = agents.id), 0), '0') AS UNSIGNED)"
        query = query.annotate(exp_years=RawSQL(exp_sql, ()))

        sort_by = req.sort_by or ('distance' if (user_lat is not None and user_lng is not None) else 'match')

        # Apply strict DB sorting to ensure efficient limiting
        if user_lat is not None and user_lng is not None and sort_by == 'distance':
            query = query.order_by('distance_db', '-padosi_smart_rank', '-exp_years')
        elif sort_by == 'rating':
            query = query.order_by('-padosi_smart_rank', 'distance_db', '-exp_years') 
        elif sort_by == 'experience':
            query = query.order_by('-exp_years', '-padosi_smart_rank', 'distance_db')
        else:
            query = query.order_by('-padosi_smart_rank', 'distance_db', '-exp_years')

        # Limit strictly to 3 records at database level
        query = query[:3]
        
        return query, user_lat, user_lng, invalid_pincode


    @staticmethod
    def search_agents(req: FindAgentsRequest) -> FindAgentsResponse:
        """
        Executes Find Agent search using efficient DB limit (Top 3) without fetching all agents into memory.
        """
        query, user_lat, user_lng, invalid_pincode = AgentSearchService._build_agent_queryset(req)
        
        page_agents = list(query)
        detected_area = req.location or req.pincode or ""
        
        # Max smart rank logic
        max_smart_rank = 165.0
        if page_agents:
            max_smart_rank = max(165.0, float(max([getattr(a, 'padosi_smart_rank', 0) for a in page_agents])))
        
        # Update match percent dynamically
        for a in page_agents:
            rank = getattr(a, 'padosi_smart_rank', 0) or 0
            a.match_percent = int(min(99.0, max(80.0, 80.0 + (rank / max_smart_rank) * 19.0)))
            a.distance = getattr(a, 'distance_db', None)
            if a.distance and a.distance >= 999999:
                a.distance = None

        serialized_agents: List[AgentCardSchema] = []
        for agent in page_agents:
            profile = agent.get_primary_profile()
            perf = getattr(agent, 'performanceStats', None)

            photo_url = profile.profile_photo_url if profile else '/static/img/avatar-icon.jpg'

            badge_objs: List[RecognitionBadge] = []
            for b in (agent.badge_list or []):
                badge_objs.append(RecognitionBadge(
                    class_name=b.get('class', 'badge-verified-official'),
                    icon=b.get('icon', 'fa-check-circle'),
                    label=b.get('label', '')
                ))

            dist_val = agent.distance if (agent.distance is not None and agent.distance < 999999) else None

            claims_processed_val = int(perf.claims_processed) if (perf and perf.claims_processed) else 0
            formatted_claims_processed_val = perf.formatted_claims_processed if (perf and hasattr(perf, 'formatted_claims_processed')) else str(claims_processed_val)

            claims_amount_val = float(perf.claims_amount) if (perf and perf.claims_amount) else 0.0
            formatted_claims_amount_val = perf.formatted_claims_amount if (perf and hasattr(perf, 'formatted_claims_amount')) else '0'

            serialized_agents.append(AgentCardSchema(
                id=agent.id,
                display_name=agent.display_name,
                fullname=agent.fullname,
                profile_photo_url=photo_url,
                experience_years=agent.experience_years,
                experience_range=agent.experience_range or '',
                client_base=str(agent.client_base or '0'),
                formatted_client_base=agent.formatted_client_base,
                badge=agent.badge or '',
                badges=badge_objs,
                profession=agent.profession or 'LIC Agent',
                average_rating=round(float(agent.average_rating or 0.0), 1),
                review_count=agent.review_count,
                star_rating_list=agent.star_rating_list,
                claims_processed=claims_processed_val,
                formatted_claims_processed=formatted_claims_processed_val,
                claims_amount=claims_amount_val,
                formatted_claims_amount=formatted_claims_amount_val,
                distance_km=dist_val,
                has_distance=agent.has_distance,
                formatted_distance=agent.formatted_distance,
                padosi_smart_rank=float(getattr(agent, 'padosi_smart_rank', 0.0) or 0.0),
                match_percent=getattr(agent, 'match_percent', 85),
                match_color_class=agent.match_color_class,
                insurance_segments=agent.ordered_insurance_segments,
                agent_city_display=agent.agent_city_display,
                agent_slug=agent.agent_slug,
                mobile=agent.mobile or '',
                whatsapp_raw=agent.whatsapp_raw or '',
                whatsapp_digits=profile.whatsapp_digits if profile else '',
                is_approved_by_admin=agent.is_approved_by_admin,
                is_verified_agent=agent.is_verified_agent,
                is_trusted=agent.is_trusted,
            ))

        filters_applied = {
            'pincode': req.pincode,
            'location': req.location,
            'lat': req.lat,
            'lng': req.lng,
            'service_types': req.service_types,
            'insurance_types': req.insurance_types,
            'insurance_companies': req.insurance_companies,
            'claim_insurance_company': req.claim_insurance_company,
            'complaint_type': req.complaint_type,
            'search': req.search,
            'sort_by': req.sort_by,
        }

        pagination = PaginationMeta(
            total_records=len(page_agents),
            current_page=1,
            total_pages=1,
            page_size=3,
            has_next=False,
            has_previous=False,
            next_page_number=None,
            previous_page_number=None,
        )

        message = "Agents retrieved successfully." if len(page_agents) > 0 else "No agents found matching the criteria."

        return FindAgentsResponse(
            success=True,
            message=message,
            detected_area=detected_area,
            invalid_pincode=invalid_pincode,
            sort_by=req.sort_by or 'match',
            max_smart_rank=float(max_smart_rank),
            pagination=pagination,
            filters_applied=filters_applied,
            agents=serialized_agents
        )
