import os
import sys
import logging
from typing import List, Tuple, Any, Dict

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

from apps.home.views.pages import fetch_filtered_agents_list
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
    def search_agents(req: FindAgentsRequest) -> FindAgentsResponse:
        """
        Executes Find Agent search using existing Django ORM logic and returns structured JSON response.
        Does NOT alter existing Django session, database, or UI behavior.
        """
        get_dict = {
            'pincode': req.pincode or '',
            'location': req.location or '',
            'lat': str(req.lat) if req.lat is not None else '',
            'lng': str(req.lng) if req.lng is not None else '',
            'ServiceType': req.service_types or [],
            'InsuranceType': req.insurance_types or [],
            'InsuranceCompany': req.insurance_companies or [],
            'ClaimInsuranceCompany': req.claim_insurance_company or '',
            'ComplaintType': req.complaint_type or '',
            'search': req.search or '',
            'sort_by': req.sort_by or '',
        }

        session_dict = {}
        if req.pincode:
            session_dict['last_pincode'] = req.pincode.strip()
        if req.location:
            session_dict['last_location'] = req.location.strip()
        if req.lat is not None:
            session_dict['last_lat'] = str(req.lat).strip()
        if req.lng is not None:
            session_dict['last_lng'] = str(req.lng).strip()

        mock_req = MockRequest(get_dict, session_dict)

        # Call existing Django business logic function
        all_agents, user_lat, user_lng, sort_by, invalid_pincode, max_smart_rank = fetch_filtered_agents_list(mock_req)
        detected_area = mock_req.session.get('detected_area', '')

        # Calculate pagination
        total_records = len(all_agents)
        page_size = req.page_size if req.page_size > 0 else 10
        total_pages = max(1, (total_records + page_size - 1) // page_size)
        current_page = min(max(1, req.page), total_pages)

        start_idx = (current_page - 1) * page_size
        end_idx = start_idx + page_size
        page_agents = all_agents[start_idx:end_idx]

        has_next = current_page < total_pages
        has_previous = current_page > 1
        next_page_number = (current_page + 1) if has_next else None
        previous_page_number = (current_page - 1) if has_previous else None

        # Serialize agents to Pydantic AgentCardSchema
        serialized_agents: List[AgentCardSchema] = []
        for agent in page_agents:
            profile = getattr(agent, 'profile', None)
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
                match_percent=int(agent.calculated_match_percent),
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
            'sort_by': sort_by,
        }

        pagination = PaginationMeta(
            total_records=total_records,
            current_page=current_page,
            total_pages=total_pages,
            page_size=page_size,
            has_next=has_next,
            has_previous=has_previous,
            next_page_number=next_page_number,
            previous_page_number=previous_page_number,
        )

        message = "Agents retrieved successfully." if total_records > 0 else "No agents found matching the criteria."

        return FindAgentsResponse(
            success=True,
            message=message,
            detected_area=detected_area,
            invalid_pincode=invalid_pincode,
            sort_by=sort_by,
            max_smart_rank=float(max_smart_rank),
            pagination=pagination,
            filters_applied=filters_applied,
            agents=serialized_agents
        )
