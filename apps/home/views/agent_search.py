"""Agent search helpers: dropdown data, nearest-pincode lookup, build_agent_query (chatbot) and AI-picks serialization."""
import re
import math
import logging
from apps.agents.models import Agent, AgentPortfolio
from apps.home.models import Pincode
from apps.home.services.agent_filters import (
    apply_insurance_product_filter,
    apply_insurance_type_filter,
    apply_location_text_filter,
    listed_agents_queryset,
)
from apps.home.services.distance import (
    DistanceService,
    rank_directory_agents,
)
from apps.home.services.geocoding import GeocodingService
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.core.cache import cache

# Keep the original logger name so log lines/filters are unchanged.
logger = logging.getLogger('apps.home.views.pages')


def get_portfolio_companies_by_type():
    """
    Get companies grouped by insurance type (segment).
    Cache for 30 minutes.
    """
    cache_key = 'portfolio_companies_by_type'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    segment_label_map = {
        'health': 'Health Insurance',
        'life': 'Life Insurance',
        'motor': 'Motor Insurance',
        'sme': 'SME Insurance',
    }

    companies_by_type = {
        'Health Insurance': [],
        'Life Insurance': [],
        'Motor Insurance': [],
        'SME Insurance': [],
    }

    try:
        # Fetch active agents portfolios
        portfolios = AgentPortfolio.objects.filter(
            agent__status='active',
        ).select_related('agent')

        for p in portfolios:
            segment_key = str(p.segment_type).lower().strip()
            if segment_key not in segment_label_map:
                continue

            bucket = segment_label_map[segment_key]
            candidates = []

            primary = p.primary_companies or {}
            secondary = p.secondary_companies or {}

            primary_name = str(primary.get('name', '')).strip()
            secondary_name = str(secondary.get('name', '')).strip()

            if primary_name:
                candidates.append(primary_name)
            if secondary_name:
                candidates.append(secondary_name)

            extra_companies = secondary.get('companies', [])
            if isinstance(extra_companies, list):
                for c in extra_companies:
                    if isinstance(c, dict):
                        c_name = str(c.get('name', '')).strip()
                    else:
                        c_name = str(c).strip()
                    if c_name:
                        candidates.append(c_name)

            for name in candidates:
                companies_by_type[bucket].append(name)
    except Exception as e:
        logger.error(f"Error fetching portfolio companies: {e}")

    # Dedup and sort
    for label, lst in companies_by_type.items():
        deduped = {}
        for company in lst:
            key = company.lower().strip()
            if key and key not in deduped:
                deduped[key] = company.strip()
        companies_by_type[label] = sorted(list(deduped.values()), key=str.casefold)

    cache.set(cache_key, companies_by_type, timeout=1800)
    return companies_by_type


def _find_closest_pincode(lat, lng, max_km=50.0):
    """
    Find closest pincode using a bounding-box pre-filter to leverage indexes
    and avoid expensive full-table acos() calculations across all pincodes.
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (ValueError, TypeError):
        return None

    lat_delta = max_km / 111.0
    cos_lat = max(0.1, math.cos(math.radians(lat)))
    lng_delta = max_km / (111.0 * cos_lat)

    return Pincode.objects.filter(
        latitude__range=(lat - lat_delta, lat + lat_delta),
        longitude__range=(lng - lng_delta, lng + lng_delta),
    ).annotate(
        distance=RawSQL(
            "(6371 * acos(cos(radians(%s)) * cos(radians(latitude)) * cos(radians(longitude) - radians(%s)) + sin(radians(%s)) * sin(radians(latitude))))",
            (lat, lng, lat)
        )
    ).order_by('distance').first()



def get_all_claim_companies():
    """
    Return a sorted, deduplicated list of all insurance company names
    that active agents have added to their profile (Agent.insurance_companies JSON field).
    Cached for 30 minutes to avoid repeated DB hits.
    """
    cache_key = 'all_claim_companies_v1'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from django.db import connection
        with connection.cursor() as cursor:
            # MySQL JSON_TABLE to extract each element from the JSON array
            cursor.execute(
                """
                SELECT DISTINCT jt.company_name
                FROM agents,
                JSON_TABLE(
                    agents.insurance_companies,
                    '$[*]' COLUMNS (company_name VARCHAR(255) PATH '$')
                ) AS jt
                WHERE agents.status = 'active'
                AND jt.company_name IS NOT NULL
                AND jt.company_name != ''
                ORDER BY jt.company_name
                """
            )
            rows = cursor.fetchall()
            companies = [r[0].strip() for r in rows if r[0] and r[0].strip()]
    except Exception:
        # Fallback: Python-side extraction (slower but safe)
        try:
            companies_raw = (
                Agent.objects
                .filter(status='active')
                .exclude(insurance_companies__isnull=True)
                .values_list('insurance_companies', flat=True)
            )
            seen = {}
            for raw in companies_raw:
                if not raw:
                    continue
                items = raw if isinstance(raw, list) else []
                for item in items:
                    if item and isinstance(item, str) and item.strip():
                        key = item.strip().lower()
                        if key not in seen:
                            seen[key] = item.strip()
            companies = sorted(seen.values(), key=str.casefold)
        except Exception:
            companies = []

    cache.set(cache_key, companies, timeout=1800)
    return companies

def build_agent_query(pincode, location, lat, lng, detected_area, service_type_input, insurance_type_input, insurance_company_input, claim_company_input, search_val, sort_by, request=None):
    invalid_pincode = False
    query = listed_agents_queryset()
    query = query.select_related('profile', 'performanceStats').prefetch_related(
        'insuranceSegments', 'reviews', 'serviceableCities', 'productExpertise', 'servicePincodes'
    )

    query, db_types = apply_insurance_type_filter(query, insurance_type_input)

    if service_type_input:
        q_pref = Q()
        if any(s in ['New Policy', 'Buying new insurance'] for s in service_type_input):
            q_pref |= Q(leadPreferences__leads_new_business=True)
        if any(s in ['Claim Assistance', 'Claim'] for s in service_type_input):
            q_pref |= Q(leadPreferences__leads_claims_support=True)
        if any(s in ['Policy Review', 'Insurance audit', 'Port / transfer'] for s in service_type_input):
            q_pref |= Q(leadPreferences__leads_portfolio_analysis=True)

        q_spec = Q()
        if db_types:
            q_spec = Q(insuranceSegments__segment_type__in=db_types)

        q_no_pref = Q(leadPreferences__isnull=True)
        query = query.filter(q_pref | q_spec | q_no_pref).distinct()

    has_coords = bool(lat and lng)
    query = apply_location_text_filter(query, location, pincode=pincode, has_coords=has_coords)
    query = apply_insurance_product_filter(query, insurance_company_input, db_types)

    claim_company_input = (claim_company_input or '').strip()
    if claim_company_input:
        query = query.filter(
            Q(portfolios__primary_companies__icontains=claim_company_input) |
            Q(portfolios__secondary_companies__icontains=claim_company_input)
        ).distinct()
    
    search_val = (search_val or '').strip()
    if search_val:
        query = query.filter(
            Q(fullname__icontains=search_val) |
            Q(profile__state__icontains=search_val)
        ).distinct()
    
    # Location check and API geocoding Fallback
    user_lat = None
    user_lng = None
    if lat and lng:
        try:
            user_lat = float(lat)
            user_lng = float(lng)
        except (ValueError, TypeError):
            pass
    
    if not user_lat and not user_lng and pincode:
        if not re.match(r'^[1-9]\d{5}$', pincode):
            invalid_pincode = True
        else:
            coords = None
            try:
                geo_svc = GeocodingService()
                coords = geo_svc.resolve_coordinates(pincode)
            except Exception:
                coords = None
            if not coords or coords.get('regional_fallback'):
                p_coords = DistanceService.get_pincode_coordinates(pincode)
                if p_coords:
                    coords = p_coords
            if coords and not coords.get('regional_fallback'):
                user_lat = coords['lat']
                user_lng = coords['lng']
            # Valid 6-digit pins still match agents who list that service pincode.
    
    if invalid_pincode:
        query = query.none()
    
    # Proximity reverse-geocoding for detectedArea area name
    needs_area_res = (
        not detected_area or
        bool(re.match(r'^(Area|Region)\s+\d', detected_area, re.IGNORECASE)) or
        detected_area.startswith('PIN:') or
        bool(re.match(r'^\d{6}$', detected_area))
    )
    if user_lat and user_lng and needs_area_res:
        try:
            pincode_match = _find_closest_pincode(user_lat, user_lng, max_km=50.0)
            
            resolved_from_db = False
            if pincode_match and pincode_match.distance < 50:
                candidate = pincode_match.office_name or pincode_match.district
                if candidate and not re.match(r'^(Area|Region)\s+\d', candidate, re.IGNORECASE):
                    detected_area = pincode_match.formatted_location
                    resolved_from_db = True
            
            if not resolved_from_db:
                geo_svc = GeocodingService()
                detected_area = geo_svc.reverse_geocode(user_lat, user_lng)
        except Exception as e:
            logger.warning(f"find_agents: reverse geocoding failed: {e}")
            
        if detected_area and request:
            request.session['detected_area'] = detected_area
    
    if not detected_area and pincode:
        try:
            pincode_row = Pincode.objects.filter(pincode=pincode).first()
            if pincode_row:
                detected_area = pincode_row.formatted_location
            else:
                detected_area = f"PIN: {pincode}"
        except Exception:
            detected_area = f"PIN: {pincode}"
        if request:
            request.session['detected_area'] = detected_area
    
    if user_lat and user_lng and request:
        request.session['lat'] = str(user_lat)
        request.session['lng'] = str(user_lng)
    
    if not sort_by:
        sort_by = 'rating'
    
    # Inject Padosi Smart Rank score calculation (MySQL-specific)
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
                (SELECT last_login_at FROM users WHERE users.email = agents.email),
                (SELECT last_login FROM auth_user WHERE auth_user.id = agents.user_id)
            ) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 3 DAY) THEN 50
            WHEN COALESCE(
                (SELECT last_login_at FROM users WHERE users.email = agents.email),
                (SELECT last_login FROM auth_user WHERE auth_user.id = agents.user_id)
            ) >= DATE_SUB(UTC_TIMESTAMP(), INTERVAL 14 DAY) THEN 25
            WHEN COALESCE(
                (SELECT last_login_at FROM users WHERE users.email = agents.email),
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
    
    # Fetch and process/sort in memory
    all_agents = list(query)
    
    for agent in all_agents:
        agent.distance = None

    all_agents = rank_directory_agents(all_agents, user_lat, user_lng, search_pincode=pincode)

    def _nearby_rank(agent):
        return 0 if getattr(agent, 'is_nearby', False) else 1

    # In-memory sorting matching Laravel's logic
    if user_lat is not None and user_lng is not None and sort_by == 'distance':
        all_agents.sort(key=lambda x: (
            x.distance if x.distance is not None else 999999,
            -(x.padosi_smart_rank or 0),
        ))
    elif sort_by == 'rating':
        all_agents.sort(key=lambda x: (_nearby_rank(x), -x.average_rating, -(x.padosi_smart_rank or 0)))
    elif sort_by == 'experience':
        all_agents.sort(key=lambda x: (_nearby_rank(x), -x.experience_years, -(x.padosi_smart_rank or 0)))
    else:
        # Default: best match % (smart_rank desc), tiebreaker: distance asc
        all_agents.sort(key=lambda x: (
            _nearby_rank(x),
            -(x.padosi_smart_rank or 0),
            x.distance if x.distance is not None else 999999,
        ))

    # Calculate match percentage and attach reviews/stats properties
    max_smart_rank = max([a.padosi_smart_rank or 0 for a in all_agents]) if all_agents else 165
    if max_smart_rank <= 0:
        max_smart_rank = 165

    for a in all_agents:
        rank = a.padosi_smart_rank or 0
        a.match_percent = int(min(99.0, max(80.0, 80.0 + (rank / max_smart_rank) * 19.0)))
        # Attach helper attributes for templates
        a.review_count_val = a.review_count

    return all_agents, max_smart_rank, invalid_pincode, detected_area


def serialize_agent_for_ai_picks(agent, user_lat, user_lng):
    from apps.agents.services.license_status import is_irdai_license_active

    profile = agent.get_primary_profile()
    perf = getattr(agent, 'performanceStats', None)
    
    # Calculate profile completeness
    comp_score = 15
    if profile:
        if profile.address and profile.languages:
            comp_score += 15
        if getattr(profile, 'service_pincodes', None) and agent.serviceableCities.exists():
            comp_score += 15
        if agent.insuranceSegments.exists():
            comp_score += 15
        if hasattr(agent, 'portfolios') and agent.portfolios.exists():
            comp_score += 15
        if profile.profile_photo_path:
            comp_score += 10
        if hasattr(agent, 'leadPreferences') and agent.leadPreferences:
            comp_score += 15
    if agent.status == 'pending':
        comp_score = 100
    comp_score = min(comp_score, 100)

    # Calculate response rate
    try:
        resp_time = float(perf.response_time) if (perf and perf.response_time is not None) else 2.0
    except (ValueError, TypeError):
        resp_time = 2.0
    resp_rate = int(max(70.0, min(100.0, 100.0 - (resp_time * 1.5))))

    # Insurance types labels mapping
    segments = agent.ordered_insurance_segments
    insurance_types = [s.capitalize() if s != 'sme' else 'SME' for s in segments]

    # Investment types
    investment_types = []
    if profile and profile.normalized_investment_types:
        investment_types = [i.capitalize() for i in profile.normalized_investment_types]

    # Client base clean
    try:
        clients = int(agent.client_base or 0)
    except (ValueError, TypeError):
        clients = 0

    return {
        'id': agent.id,
        'name': agent.display_name,
        'profile_photo': agent.profile.profile_photo_url if profile else '/static/img/avatar-icon.jpg',
        'is_verified': agent.is_verified_agent,
        'is_trusted': agent.is_trusted,
        'experience_years': agent.experience_years,
        'experience_display': f"{agent.experience_years}+ yr" if agent.experience_years else "N/A",
        'rating': round(agent.average_rating, 1) if agent.average_rating else 0.0,
        'reviews': agent.review_count,
        'match_score': agent.calculated_match_percent,
        'distance': agent.distance if (agent.distance is not None and agent.distance != 999999) else None,
        'distance_display': agent.formatted_distance if (agent.distance is not None and agent.distance != 999999) else "—",
        'location': f"{agent.agent_city_display or ''}, {profile.state or ''}".strip(', ') if profile else "N/A",
        'happy_clients': clients,
        'claims_settled': (int(perf.claims_settled) if (perf and perf.claims_settled is not None and str(perf.claims_settled).isdigit()) else 0) if perf else 0,
        'insurance_types': insurance_types,
        'investment_types': investment_types,
        'irdai_verified': is_irdai_license_active(profile) if profile else False,
        'amfi_verified': bool(profile.arn_number) if profile else False,
        'languages': profile.languages if (profile and profile.languages) else "N/A",
        'response_rate': resp_rate,
        'profile_completion': comp_score,
    }


def _html_escape_payload(value):
    """HTML-escape every string in a JSON-able structure bound for innerHTML."""
    import html as _html
    if isinstance(value, str):
        return _html.escape(value, quote=True)
    if isinstance(value, dict):
        return {k: _html_escape_payload(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_html_escape_payload(v) for v in value]
    return value
