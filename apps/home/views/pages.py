from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_cookie
import re
import math
import logging
import json
import requests as http_requests
from apps.home.models.site_setting import SiteSetting
from apps.home.models.faq import Faq
from apps.home.services.homepage import build_homepage_cms_context
from django.contrib.staticfiles.storage import staticfiles_storage


def favicon(request):
    url = SiteSetting.get_value('site_favicon', '')
    if url:
        return redirect(url)
    return redirect(staticfiles_storage.url('favicon.ico'))
from apps.admin_panel.models.contact_submission import ContactSubmission
from apps.agents.models import Agent, AgentPortfolio, AgentReview, FavoriteAgent
from apps.home.models import Pincode
from apps.home.services.agent_filters import (
    apply_insurance_product_filter,
    apply_insurance_type_filter,
    apply_location_text_filter,
    listed_agents_queryset,
)
from apps.home.services.distance import (
    FIND_AGENTS_PAGE_SIZE,
    directory_result_window,
    DistanceService,
    rank_directory_agents,
)
from apps.home.services.geocoding import GeocodingService
from apps.home.services.ai_picks import AIPicksService
from apps.home.services.matching import assign_match_percents
from apps.home.services.avatar_thumbs import small_avatar_url
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.expressions import RawSQL
from django.core.paginator import Paginator
from django.core.cache import cache
from .leads import CONTACT_MAX_PER_IP, CONTACT_WINDOW_SECONDS, QUICK_LEAD_MAX_PER_IP, QUICK_LEAD_WINDOW_SECONDS, _rate_limited, _is_honeypot_hit, contact_submit, quick_lead_capture  # noqa: F401
from .homepage import _reviews_json_for_script, _organization_schema, home  # noqa: F401
from .agent_search import get_portfolio_companies_by_type, _find_closest_pincode, get_all_claim_companies, build_agent_query, serialize_agent_for_ai_picks, _html_escape_payload  # noqa: F401
from .pincode import pincode_fetch, _get_or_create_pincode, _pincode_matching_agents, check_pincode, check_pincode_agents  # noqa: F401
from .city_directory import _AREA_PINCODE_MAP, MIN_INDEXABLE_CITY_AGENTS, JUNK_CITY_SLUGS, _resolve_area_to_pincodes, CITY_CATEGORIES, SERVICE_PAGES, STATE_HUBS, _state_city_q, state_hub_agents, filter_agents_for_category, _directory_path, city_agents_directory  # noqa: F401

logger = logging.getLogger(__name__)
# One analytics thread per (pincode, result set) per window; crawlers re-running a search spawn nothing.
SEARCH_TRACK_DEDUPE_SECONDS = 10 * 60


def about(request):
    about_content = SiteSetting.get_value('about_page_content', {
        'banner_title': 'About Us',
        'banner_subtitle': 'Connecting you with trusted insurance agents in your neighborhood',
        'who_we_are': 'PadosiAgent is a digital-first platform built to simplify how people connect with trusted insurance professionals in their locality.',
        'why_we_exist': 'The insurance ecosystem often faces three common challenges.',
        'what_we_do': 'We provide a platform where customers can discover agents based on location and service segments.',
        'vision': "To build India's most trusted hyperlocal insurance discovery and service platform.",
        'mission': 'Digitally empower insurance agents. Promote transparency and accountability.',
        'commitment': 'PadosiAgent does not replace insurers, brokers, or regulatory authorities.',
    })
    return render(request, 'public/about.html', {'about': about_content})


@vary_on_cookie
@cache_page(60 * 60 * 2)
def terms(request):
    return render(request, 'public/terms.html')


@vary_on_cookie
@cache_page(60 * 60 * 2)
def privacy(request):
    return render(request, 'public/privacy.html')


def faq(request):
    faq_content = SiteSetting.get_value('faq_page_content', {
        'title': "Got Questions? I've Got Your Answers",
        'subtitle': 'Everything you need to know before finding your PadosiAgent',
    })

    faqs = list(Faq.objects.filter(is_active=True).order_by('sort_order', 'id'))
    half = -(-len(faqs) // 2)  # ceiling division — same as Laravel's ceil($faqs->count() / 2)
    faqs_left  = faqs[:half]
    faqs_right = faqs[half:]

    return render(request, 'public/faq.html', {
        'faq_content': faq_content,
        'faqs_left':   faqs_left,
        'faqs_right':  faqs_right,
    })


def contact(request):
    """Public Contact page — renders banner + contact form."""
    contact_content = SiteSetting.get_value('contact_page_content', {
        'banner_title':    'Contact Us',
        'section_title':   'Secure Your Family Future With us.',
        'section_subtitle': "Have questions or need assistance? Reach out to us today for expert guidance on securing your family's future.",
    })
    return render(request, 'public/contact.html', {'contact': contact_content})


def fetch_filtered_agents_list(request):
    pincode = (request.GET.get('pincode') or request.session.get('last_pincode', '')).strip()
    location = (request.GET.get('location') or request.session.get('last_location', '')).strip()
    lat = (request.GET.get('lat') or request.session.get('last_lat', '')).strip()
    lng = (request.GET.get('lng') or request.session.get('last_lng', '')).strip()
    detected_area = request.GET.get('detected_area') or request.session.get('detected_area', '')

    service_type_input = request.GET.getlist('ServiceType')

    # Core query build — do not require auth_user; PHP-imported agents often have none.
    query = listed_agents_queryset()
    # Rating/count come from two scalar subqueries instead of prefetching every review (audit WEB8).
    approved_reviews = AgentReview.objects.filter(agent_id=OuterRef('pk'), is_approved=True).order_by().values('agent_id')
    query = query.select_related('profile', 'performanceStats').prefetch_related(None).prefetch_related(
        'insuranceSegments', 'serviceableCities', 'productExpertise', 'servicePincodes',
        'achievementPhotos', 'subscriptions',
    ).annotate(
        approved_review_sum=Subquery(approved_reviews.annotate(s=Sum('rating')).values('s')),
        approved_review_n=Subquery(approved_reviews.annotate(n=Count('id')).values('n')),
    )

    insurance_type_input = request.GET.getlist('InsuranceType')
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

    insurance_company_input = request.GET.getlist('InsuranceCompany')
    query = apply_insurance_product_filter(query, insurance_company_input, db_types)

    claim_company_input = request.GET.get('ClaimInsuranceCompany', '').strip()
    # NOTE: We do NOT hard-filter by claim company — we want ALL agents to appear,
    # but company-matched agents appear at the top with higher match %.
    # Matching logic is applied in-memory after fetching.

    search_val = request.GET.get('search', '').strip()
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

    invalid_pincode = False
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
            # Valid 6-digit pins still match agents who list that service pincode
            # even when geocoding cannot produce coordinates.

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
            exact = DistanceService.get_precise_pincode_coordinates(pincode) if pincode else None
            if exact and exact.get('office_name'):
                detected_area = f"{exact['office_name']}, {exact.get('district', '')}".strip(', ')
            else:
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
            
        if detected_area:
            _set_session_if_changed(request.session, 'detected_area', detected_area)

    if not detected_area and pincode:
        try:
            exact = DistanceService.get_precise_pincode_coordinates(pincode)
            if exact and exact.get('office_name'):
                detected_area = f"{exact['office_name']}, {exact.get('district', '')}".strip(', ')
            else:
                pincode_row = Pincode.objects.filter(pincode=pincode).first()
                if pincode_row:
                    detected_area = pincode_row.formatted_location
                else:
                    detected_area = f"PIN: {pincode}"
        except Exception:
            detected_area = f"PIN: {pincode}"
        _set_session_if_changed(request.session, 'detected_area', detected_area)

    if user_lat and user_lng:
        _set_session_if_changed(request.session, 'lat', str(user_lat))
        _set_session_if_changed(request.session, 'lng', str(user_lng))

    sort_by = request.GET.get('sort_by', '').strip()
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

    # Add claim company boost to smart_rank if a claim company was selected.
    # Agents whose insurance_companies JSON contains the searched company get +60 pts.
    if claim_company_input:
        claim_boost_sql = f'(CASE WHEN JSON_CONTAINS(IFNULL(agents.insurance_companies, \'[]\'::JSON), JSON_QUOTE(%s)) THEN 60 ELSE 0 END)'
        # Use standard MySQL-compatible syntax (no ::JSON cast)
        claim_boost_sql = '(CASE WHEN JSON_CONTAINS(IFNULL(agents.insurance_companies, \'[]\'), JSON_QUOTE(%s)) THEN 60 ELSE 0 END)'
        claim_boost_params = (claim_company_input,)
    else:
        claim_boost_sql = '0'
        claim_boost_params = ()

    all_rank_params = filter_match_params + claim_boost_params

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
        ({filter_match_sql} * 30) +
        {claim_boost_sql}
    """

    query = query.annotate(padosi_smart_rank=RawSQL(smart_rank_expr, all_rank_params))
    # Fetch all listed agents — plan type does not gate public directory visibility.
    # All active agents with visible cards appear in the directory.
    all_agents = list(query)

    # Tag each agent with whether they match the claim company (for match % adjustment)
    claim_company_lower = claim_company_input.lower() if claim_company_input else ''
    for agent in all_agents:
        agent.distance = None
        # Same values Agent.average_rating / review_count compute from prefetched reviews.
        agent._review_count = int(agent.approved_review_n or 0)
        agent._avg_rating = (
            int(agent.approved_review_sum or 0) / agent._review_count if agent._review_count else 0.0
        )
        if claim_company_lower:
            companies = agent.insurance_companies or []
            if isinstance(companies, list):
                agent.has_claim_company_match = any(
                    claim_company_lower in str(c).lower() for c in companies
                )
            else:
                agent.has_claim_company_match = False
        else:
            agent.has_claim_company_match = None  # No filter active

    # Nearby/pin matches first; farther agents stay available for Load More.
    all_agents = rank_directory_agents(all_agents, user_lat, user_lng, search_pincode=pincode)

    def _nearby_rank(agent):
        # Keep local matches on page 1; Load More pages get farther agents.
        return 0 if getattr(agent, 'is_nearby', False) else 1

    # When claim company is selected: company-matched agents come first (tier 0),
    # non-matched come after (tier 1) within same sort.
    def _claim_tier(agent):
        if claim_company_lower and getattr(agent, 'has_claim_company_match', False):
            return 0  # Matched — top section
        elif claim_company_lower:
            return 1  # Not matched — shown below
        return 0  # No filter — all equal

    # In-memory sorting matching Laravel's logic
    if user_lat is not None and user_lng is not None and sort_by == 'distance':
        all_agents.sort(key=lambda x: (
            _claim_tier(x),
            x.distance if x.distance is not None else 999999,
            -(x.padosi_smart_rank or 0),
        ))
    elif sort_by == 'rating':
        all_agents.sort(key=lambda x: (_claim_tier(x), _nearby_rank(x), -x.average_rating, -(x.padosi_smart_rank or 0)))
    elif sort_by == 'experience':
        all_agents.sort(key=lambda x: (_claim_tier(x), _nearby_rank(x), -x.experience_years, -(x.padosi_smart_rank or 0)))
    else:
        # Default: best match % (smart_rank desc), tiebreaker: distance asc
        all_agents.sort(key=lambda x: (
            _claim_tier(x),
            _nearby_rank(x),
            -(x.padosi_smart_rank or 0),
            x.distance if x.distance is not None else 999999,
        ))

    # Calculate match percentage with claim company awareness:
    # - Company-matched agents: 88-99% range (higher band)
    # - Non-matched agents:     72-85% range (lower band)
    # - No filter active:       80-99% range (normal)
    assign_match_percents(all_agents, claim_company_lower)
    for a in all_agents:
        a.review_count_val = a.review_count

    max_smart_rank = max([a.padosi_smart_rank or 0 for a in all_agents]) if all_agents else 165
    if max_smart_rank <= 0:
        max_smart_rank = 165

    return all_agents, user_lat, user_lng, sort_by, invalid_pincode, max_smart_rank


def _set_session_if_changed(session, key, value):
    # Assigning marks a cached_db session dirty, i.e. one DB write per search (audit WEB9).
    if session.get(key) != value:
        session[key] = value


def _coords_in_india(lat, lng):
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return 6.5 <= lat_f <= 37.5 and 68.0 <= lng_f <= 97.5  # NaN fails both comparisons


def find_agents(request):
    sort_by = request.GET.get('sort_by', '').strip()
    invalid_pincode = False

    # RESET LOCATION
    if 'reset_location' in request.GET:
        for k in ['last_pincode', 'last_location', 'last_lat', 'last_lng', 'detected_area', 'pincode', 'location', 'lat', 'lng']:
            if k in request.session:
                del request.session[k]
        return redirect('home:find_agents')

    # Capture parameters
    pincode_param = request.GET.get('pincode', '').strip()
    location_param = request.GET.get('location', '').strip()
    lat_param = request.GET.get('lat', '').strip()
    lng_param = request.GET.get('lng', '').strip()
    detected_area = request.session.get('detected_area', '')

    is_htmx = (
        request.headers.get('HX-Request') == 'true'
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    )

    # Save to session and clear opposite parameters to prevent conflicts
    if pincode_param or location_param:
        if pincode_param:
            pincode_ok = bool(re.fullmatch(r'[1-9]\d{5}', pincode_param))
            if pincode_ok:
                _set_session_if_changed(request.session, 'last_pincode', pincode_param)
            else:
                # Never persist unchecked input; forget the previous search instead.
                request.session.pop('last_pincode', None)
            request.session.pop('last_location', None)
            detected_area = pincode_param
            
            # Resolve pincode to area name immediately (before redirect)
            if pincode_ok:
                try:
                    pincode_row = Pincode.objects.filter(pincode=pincode_param).first()
                    is_placeholder = False
                    if pincode_row:
                        office_name = pincode_row.office_name or ''
                        is_placeholder = bool(re.match(r'^(Area|Region)\s+\d', office_name, re.IGNORECASE))
                        if not is_placeholder and office_name:
                            detected_area = pincode_row.formatted_location
                        elif pincode_row.state:
                            detected_area = f"{pincode_row.state} - {pincode_param}"
                    
                    if not pincode_row or is_placeholder:
                        geo_svc = GeocodingService()
                        resolved = geo_svc.resolve_coordinates(pincode_param)
                        if resolved and resolved.get('display_name'):
                            detected_area = resolved['display_name']
                except Exception as e:
                    logger.warning(f"find_agents: Failed to resolve area for pincode {pincode_param}: {e}")
            
            if pincode_ok:
                _set_session_if_changed(request.session, 'detected_area', detected_area)
            else:
                request.session.pop('detected_area', None)

        if location_param:
            _set_session_if_changed(request.session, 'last_location', location_param)
            _set_session_if_changed(request.session, 'detected_area', location_param)
            if not pincode_param:
                request.session.pop('last_pincode', None)

        # Clear old GPS memory
        for k in ['last_lat', 'last_lng', 'lat', 'lng']:
            if k in request.session:
                del request.session[k]

    elif lat_param and lng_param and _coords_in_india(lat_param, lng_param):
        _set_session_if_changed(request.session, 'last_lat', lat_param)
        _set_session_if_changed(request.session, 'last_lng', lng_param)
        
        # Clear old Pincode/Location memory
        for k in ['last_pincode', 'last_location', 'pincode', 'location', 'detected_area']:
            if k in request.session:
                del request.session[k]

    # Merge query parameters and session values for query lookup
    pincode = (pincode_param or request.session.get('last_pincode', '')).strip()
    location = (location_param or request.session.get('last_location', '')).strip()
    lat = (lat_param or request.session.get('last_lat', '')).strip()
    lng = (lng_param or request.session.get('last_lng', '')).strip()
    detected_area = detected_area or request.session.get('detected_area', '')

    should_gate_guest = False
    service_type_input = request.GET.getlist('ServiceType')
    

    has_new_policy = 'New Policy' in service_type_input or 'Buying new insurance' in service_type_input
    has_claim_assistance = 'Claim Assistance' in service_type_input or 'Claim' in service_type_input
    has_policy_review = any(s in service_type_input for s in ['Policy Review', 'Insurance audit', 'Port / transfer'])

    policy_review_needs_type = has_policy_review and not request.GET.get('InsuranceType')
    new_policy_needs_type = has_new_policy and not request.GET.get('InsuranceType')
    claim_assistance_needs_type = has_claim_assistance and not request.GET.get('InsuranceType')
    no_service_type = not service_type_input

    should_require_filter_selection = False
    filter_prompt_message = (
        'Please select a Service Type and an Insurance Type, then click Apply.' if no_service_type else (
            'For New Policy, please select an Insurance Type and click Apply.' if new_policy_needs_type else (
                'For Claim Assistance, please select an Insurance Type and click Apply.' if claim_assistance_needs_type else (
                    'For Policy Review, please select at least one Insurance Type and click Apply.' if policy_review_needs_type else
                    'Please select at least one filter (Service Type, Insurance Type, or Insurance Company), then click Apply.'
                )
            )
        )
    )

    portfolio_companies_by_type = get_portfolio_companies_by_type()
    # Load all insurance company names for the Claim Company dropdown (cached)
    all_claim_companies = get_all_claim_companies()
    selected_claim_company = request.GET.get('ClaimInsuranceCompany', '').strip()

    if should_require_filter_selection:
        paginator = Paginator([], FIND_AGENTS_PAGE_SIZE)
        agents = paginator.page(1)
        context = {
            'agents': agents,
            'shouldGateGuest': should_gate_guest,
            'shouldRequireFilterSelection': should_require_filter_selection,
            'filterPromptMessage': filter_prompt_message,
            'detectedArea': detected_area,
            'invalidPincode': invalid_pincode,
            'next_page_url': None,
            'has_next': False,
            'hide_header': True,
        }
        if is_htmx:
            return render(request, 'partials/find-agents-list.html', context)
        context['portfolioCompaniesByType'] = portfolio_companies_by_type
        return render(request, 'public/find-agents.html', context)

    # Re-retrieve sorted agents using helper
    all_agents, user_lat, user_lng, sort_by, invalid_pincode, max_smart_rank = fetch_filtered_agents_list(request)
    detected_area = request.session.get('detected_area', '')

    # First page shows 5 agents; Load More fetches the next page.
    # A full page load with ?shown=N returns pages 1..N so a profile Back
    # button (which reloads this URL) still lists every agent already opened.
    start, end, next_page_number = directory_result_window(
        len(all_agents),
        page=request.GET.get('page', 1),
        shown=request.GET.get('shown', 1),
        is_partial=is_htmx,
    )
    agents_page = all_agents[start:end]
    has_more = next_page_number is not None

    next_page_url = None
    if has_more:
        params = request.GET.copy()
        params.pop('shown', None)
        params['page'] = next_page_number
        next_page_url = f"?{params.urlencode()}"

    if request.user.is_authenticated:
        favorite_ids = set(
            FavoriteAgent.objects.filter(user=request.user).values_list('agent_id', flat=True)
        )
    else:
        favorite_ids = set()

    # ── Profile Analytics Tracking ────────────────────────────────────────
    # All tracking is wrapped in try/except so a DB hiccup never breaks the
    # search page for visitors. Tracking only fires on real search renders
    # (not resets, not filter-gate screens).
    # Never feed an unvalidated query-string pincode into analytics / WhatsApp alerts.
    if not invalid_pincode and agents_page and (not pincode or re.fullmatch(r'[1-9]\d{5}', pincode)):
        def _async_track_search(search_pincode, agent_ids, alert_agent_ids=()):
            try:
                from django.db import close_old_connections
                close_old_connections()
                from apps.agents.models import AgentCardImpression, AgentSearchEvent
                from django.db.models import F
                from datetime import date as _date
                _today = _date.today()

                if search_pincode:
                    _se, _se_created = AgentSearchEvent.objects.get_or_create(
                        search_date=_today,
                        pincode=search_pincode,
                        defaults={'event_count': 1},
                    )
                    if not _se_created:
                        AgentSearchEvent.objects.filter(pk=_se.pk).update(event_count=F('event_count') + 1)

                if agent_ids:
                    _existing_map = {
                        ci.agent_id: ci.id
                        for ci in AgentCardImpression.objects.filter(
                            agent_id__in=agent_ids,
                            impression_date=_today,
                            search_pincode=search_pincode
                        )
                    }
                    _to_create = []
                    _update_ids = []
                    for _aid in agent_ids:
                        if _aid in _existing_map:
                            _update_ids.append(_existing_map[_aid])
                        else:
                            _to_create.append(AgentCardImpression(
                                agent_id=_aid,
                                impression_date=_today,
                                search_pincode=search_pincode,
                                impression_count=1
                            ))
                    if _to_create:
                        AgentCardImpression.objects.bulk_create(_to_create, ignore_conflicts=True)
                    if _update_ids:
                        AgentCardImpression.objects.filter(id__in=_update_ids).update(
                            impression_count=F('impression_count') + 1
                        )
            except Exception as _e:
                logger.warning(f"Analytics tracking error in find_agents: {_e}")
            try:
                if alert_agent_ids:
                    from apps.wa_agent_bot.services.notification_service import send_view_alert
                    for _aid in alert_agent_ids:
                        send_view_alert(_aid, 'card_view_alert', search_pincode)
            except Exception as _e:
                logger.warning(f"Card view WhatsApp alert error in find_agents: {_e}")
            finally:
                from django.db import close_old_connections
                close_old_connections()

        try:
            import hashlib
            import threading
            _tracked_agent_ids = [_a.id for _a in agents_page]
            _track_key = 'find_agents_track_{}_{}'.format(
                pincode or '-',
                hashlib.md5(','.join(map(str, _tracked_agent_ids)).encode()).hexdigest(),
            )
            # cache.add is atomic: only the first identical search per window starts a thread.
            if cache.add(_track_key, 1, timeout=SEARCH_TRACK_DEDUPE_SECONDS):
                # WhatsApp "your card was seen" goes only to the top N cards of the first page, never to bots.
                _alert_agent_ids = []
                if start == 0 and pincode:
                    from apps.wa_agent_bot.services.notification_service import is_bot_request, view_alert_settings
                    _va = view_alert_settings()
                    if _va['card_enabled'] and not is_bot_request(request):
                        _alert_agent_ids = _tracked_agent_ids[:_va['top_n']]
                threading.Thread(
                    target=_async_track_search,
                    args=(pincode or None, _tracked_agent_ids, _alert_agent_ids),
                    daemon=True
                ).start()
        except Exception as _t_err:
            logger.warning(f"Failed to dispatch search analytics thread: {_t_err}")
    # ── End Analytics Tracking ────────────────────────────────────────────

    context = {
        'agents': agents_page,
        'favorite_ids': favorite_ids,
        'sort_by': sort_by,
        'shouldGateGuest': should_gate_guest,
        'shouldRequireFilterSelection': should_require_filter_selection,
        'filterPromptMessage': filter_prompt_message,
        'detectedArea': detected_area,
        'pincode': pincode,
        'location': location,
        'lat': lat,
        'lng': lng,
        'maxSmartRank': max_smart_rank,
        'invalidPincode': invalid_pincode,
        'next_page_url': next_page_url,
        'next_page_number': next_page_number or '',
        'has_next': has_more,
        'selected_service_type': request.GET.getlist('ServiceType'),
        'selected_insurance_types': request.GET.getlist('InsuranceType'),
        'selected_insurance_companies': request.GET.getlist('InsuranceCompany'),
        'selected_claim_company': selected_claim_company,
        'all_claim_companies': all_claim_companies,
        'hide_header': True,
    }

    if is_htmx:
        if start > 0:
            return render(request, 'partials/find-agents-load-more.html', context)
        return render(request, 'partials/find-agents-list.html', context)

    context['portfolioCompaniesByType'] = portfolio_companies_by_type
    return render(request, 'public/find-agents.html', context)


def marketing(request):
    """Agent marketing landing page — port of Frontend\\HomeController@agentMarketing
    (route 'agent.marketing', restrict.agent → agent users redirected to their dashboard).

    Captures pincode / location / GPS coords into the session (same keys as find-agents),
    resolves a human-readable area name, then redirects to the clean URL."""
    if request.user.is_authenticated:
        try:
            if Agent.objects.filter(user=request.user).exists():
                return redirect('agents:agent_dashboard')
        except Exception:
            pass

    if request.GET.get('pincode') or request.GET.get('location'):
        if request.GET.get('pincode'):
            pincode_value = (request.GET.get('pincode') or '').strip()
            request.session['last_pincode'] = pincode_value

            detected_area = None
            if re.match(r'^[1-9][0-9]{5}$', pincode_value):
                try:
                    pincode_match = Pincode.objects.filter(pincode=pincode_value).first()
                    if pincode_match:
                        detected_area = pincode_match.formatted_location
                    else:
                        geo_svc = GeocodingService()
                        coords = geo_svc.resolve_coordinates(pincode_value)
                        if coords:
                            detected_area = geo_svc.reverse_geocode(float(coords['lat']), float(coords['lng']))
                        else:
                            coords = DistanceService.get_pincode_coordinates(pincode_value)
                            if coords:
                                detected_area = geo_svc.reverse_geocode(float(coords['lat']), float(coords['lng']))
                except Exception as e:
                    logger.warning(f"marketing: failed to resolve pincode {pincode_value}: {e}")

            request.session['detected_area'] = detected_area or f"PIN: {pincode_value}"

        if request.GET.get('location'):
            request.session['last_location'] = request.GET.get('location')
            request.session['detected_area'] = request.GET.get('location')

        for k in ['last_lat', 'last_lng', 'lat', 'lng']:
            request.session.pop(k, None)
    elif request.GET.get('lat') and request.GET.get('lng'):
        user_lat = request.GET.get('lat')
        user_lng = request.GET.get('lng')
        request.session['last_lat'] = user_lat
        request.session['last_lng'] = user_lng

        for k in ['last_pincode', 'last_location', 'pincode', 'location', 'detected_area']:
            request.session.pop(k, None)

        detected_area = None
        try:
            u_lat = float(user_lat)
            u_lng = float(user_lng)
            pincode_match = _find_closest_pincode(u_lat, u_lng, max_km=50.0)

            if pincode_match and pincode_match.distance < 50:
                detected_area = pincode_match.formatted_location
            else:
                geo_svc = GeocodingService()
                detected_area = geo_svc.reverse_geocode(u_lat, u_lng)
        except Exception as e:
            logger.warning(f"marketing: reverse geocoding failed: {e}")

        if detected_area:
            request.session['detected_area'] = detected_area

    if any(k in request.GET for k in ('pincode', 'location', 'lat')):
        return redirect(request.path)

    return render(request, 'public/marketing.html', {'hide_header': True})


def calculator(request):
    """Insurance premium calculator (client-side) — port of routes/web.php:88 inline
    closure + restrict.agent (agent users redirected to their dashboard)."""
    if request.user.is_authenticated:
        try:
            if Agent.objects.filter(user=request.user).exists():
                return redirect('agents:agent_dashboard')
        except Exception:
            pass
    return render(request, 'public/calculator.html')


def coming_soon(request):
    """Coming-soon contest landing page — port of ComingSoonController@index
    (route 'coming.soon', standalone document, no variables)."""
    return render(request, 'public/coming-soon.html')


def lic_event(request):
    """LIC agent recruitment event page — port of Frontend\\HomeController@licEvent
    (route 'lic.event', standalone document)."""
    mobile_stats = [
        {'icon': '🛡️', 'phrase': '"Buy Insurance"', 'daily': '3.8L–4.7L', 'monthly': '1.15Cr–1.42Cr', 'yearly': '13.8Cr–17Cr', 'growth': '+14.2%'},
        {'icon': '🔄', 'phrase': '"Insurance Portability"', 'daily': '5K–8.5K', 'monthly': '1.5L–2.6L', 'yearly': '18L–31L', 'growth': '+8.5%'},
        {'icon': '🎧', 'phrase': '"Claims Services"', 'daily': '80K–1.2L', 'monthly': '24L–36L', 'yearly': '2.9Cr–4.3Cr', 'growth': '+11.8%'},
        {'icon': '👥', 'phrase': '"Insurance Agents"', 'daily': '45K–70K', 'monthly': '14L–21L', 'yearly': '1.7Cr–2.5Cr', 'growth': '+21.4%'},
    ]
    trust_cards = [
        {'icon': '🛡️', 'title': 'Verified Platform', 'sub': 'Trusted by LIC DOs', 'bg': 'var(--blue-lt)'},
        {'icon': '📈', 'title': 'More Leads', 'sub': 'Grow your business', 'bg': 'var(--green-lt)'},
        {'icon': '🎧', 'title': '24/7 Support', 'sub': 'Always here for you', 'bg': 'var(--teal-lt)'},
        {'icon': '🔒', 'title': 'Secure & Private', 'sub': 'Your data is safe', 'bg': '#FDF2F8'},
    ]
    return render(request, 'public/lic-event.html', {
        'mobile_stats': mobile_stats,
        'trust_cards': trust_cards,
    })


@vary_on_cookie
@cache_page(60 * 60 * 2)
def cancellation_refund_policy(request):
    """Cancellation & refund policy — port of routes/web.php:500-502 inline closure."""
    return render(request, 'public/cancellation-refund-policy.html')


def custom_page(request, slug):
    """
    Catch-all view to render custom CMS pages, or route to agent public profile if slug matches an agent.
    """
    from apps.home.models.page import Page
    from apps.agents.views.dashboard import agent_public_profile
    from apps.agents.models import AgentProfile, Agent
    from django.http import HttpResponse, Http404

    page = Page.objects.filter(slug=slug).first()
    if page:
        # Draft check: only admins can view drafts
        is_admin = bool(request.session.get('admin_id'))
        if not page.is_active and not is_admin:
            raise Http404("Page not found")

        # Serve raw page content directly if raw code mode is active
        if page.is_raw_code:
            return HttpResponse(page.content, content_type='text/html; charset=utf-8')

        return render(request, 'public/page.html', {'page': page})

    # Check if this slug belongs to an agent public profile
    if AgentProfile.objects.filter(slug=slug).exists():
        return agent_public_profile(request, slug=slug)

    raise Http404("Page not found")


def blacklisted_agents(request):
    from apps.home.models.blacklisted_agent import BlacklistedAgent
    from django.db.models import Q
    from django.core.paginator import Paginator
    
    query = request.GET.get('q', '').strip()
    field = request.GET.get('field', 'all')
    type_filter = request.GET.get('type', '').strip()
    page = request.GET.get('page', 1)
    
    agents = BlacklistedAgent.objects.all()
    
    if query:
        if field == 'pan':
            agents = agents.filter(pan__icontains=query)
        elif field == 'agency_code':
            agents = agents.filter(agency_code__icontains=query)
        elif field == 'agent_name':
            agents = agents.filter(agent_name__icontains=query)
        elif field == 'insurer':
            agents = agents.filter(insurer__icontains=query)
        else:
            agents = agents.filter(
                Q(agent_name__icontains=query) |
                Q(pan__icontains=query) |
                Q(agency_code__icontains=query) |
                Q(insurer__icontains=query)
            )
            
    if type_filter:
        agents = agents.filter(insurer_type__iexact=type_filter)
        
    total_count = agents.count()
    
    # Get unique insurer types for filter dropdown
    insurer_types = BlacklistedAgent.objects.values_list(
        'insurer_type', flat=True
    ).distinct().exclude(
        insurer_type__isnull=True
    ).exclude(
        insurer_type=''
    ).order_by('insurer_type')
    
    paginator = Paginator(agents.order_by('agent_name'), 25)
    page_obj = paginator.get_page(page)
    
    return render(request, 'public/blacklisted_agents.html', {
        'agents': page_obj,
        'query': query,
        'field': field,
        'type_filter': type_filter,
        'total_count': total_count,
        'insurer_types': insurer_types,
        'page_obj': page_obj,
    })


def ai_picks_comparison(request):
    try:
        all_agents, user_lat, user_lng, sort_by, invalid_pincode, max_smart_rank = fetch_filtered_agents_list(request)
        
        if invalid_pincode or not all_agents:
            return JsonResponse({'success': False, 'message': 'No agents found matching the requirements.'}, status=404)
        
        # Best Match is the first agent in the sorted list
        best_match_agent = all_agents[0]
        
        # Calculate AI Picks score for each agent and choose the best one
        ai_picks_agent = None
        best_score = -1.0
        
        for agent in all_agents:
            score = AIPicksService.calculate_weighted_score(agent, agent.distance)
            if score > best_score:
                best_score = score
                ai_picks_agent = agent
                
        if not ai_picks_agent:
            ai_picks_agent = best_match_agent
            
        same_recommendation = (ai_picks_agent.id == best_match_agent.id)
        
        # Dynamic AI Explanation for AI Suggested agent
        ai_explanation = AIPicksService.generate_ai_explanation(ai_picks_agent, ai_picks_agent.distance)
        
        # Serialize agents. find-agents.html interpolates these values into HTML
        # template strings, and names/cities/languages are agent-editable, so
        # escape every string here (stored XSS on the public search page).
        ai_serialized = _html_escape_payload(serialize_agent_for_ai_picks(ai_picks_agent, user_lat, user_lng))
        best_serialized = _html_escape_payload(serialize_agent_for_ai_picks(best_match_agent, user_lat, user_lng))
        
        return JsonResponse({
            'success': True,
            'ai_agent': ai_serialized,
            'best_agent': best_serialized,
            'same_recommendation': same_recommendation,
            'ai_explanation': ai_explanation
        })
    except Exception as e:
        logger.error(f"Error in ai_picks_comparison view: {e}", exc_info=True)
        return JsonResponse({'success': False, 'message': 'Internal Server Error'}, status=500)


def resolve_home_location(request):
    """Area name, city label and coordinates for the pincode saved in the session ({} if unknown)."""
    pincode = request.session.get('last_pincode')
    if not pincode:
        return {}
    try:
        record = _get_or_create_pincode(pincode)
    except Exception:
        logger.warning('Pincode lookup failed for %s', pincode, exc_info=True)
        return {}
    if not record:
        return {}
    loc = {
        'detected_area': record.office_name or '',
        'city_label': record.district or record.office_name or '',
    }
    if record.latitude and record.longitude:
        loc['user_lat'] = float(record.latitude)
        loc['user_lng'] = float(record.longitude)
    return loc


@require_POST
def save_user_location(request):
    """
    Saves user latitude/longitude or pincode into session from global client-side Geolocation API.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    lat = str(data.get('lat', '') or '').strip()
    lng = str(data.get('lng', '') or '').strip()
    pincode = str(data.get('pincode', '') or '').strip()

    if lat and lng:
        request.session['last_lat'] = lat
        request.session['last_lng'] = lng
        for k in ['last_pincode', 'last_location', 'pincode', 'location', 'detected_area']:
            request.session.pop(k, None)
        try:
            lat_f, lng_f = float(lat), float(lng)
        except (TypeError, ValueError):
            lat_f = lng_f = None
        # Bounded to India, and one external reverse-geocode per IP per minute (audit WEB4).
        from apps.admin_panel.middleware import ThreatMonitorMiddleware
        in_india = (
            lat_f is not None and lng_f is not None
            and lat_f == lat_f and lng_f == lng_f  # reject NaN
            and 6.5 <= lat_f <= 37.5 and 68.0 <= lng_f <= 97.5
        )
        rl_key = f'rl_reverse_geocode_{ThreatMonitorMiddleware.get_client_ip(request)}'
        if in_india and cache.add(rl_key, 1, timeout=60):
            try:
                area = GeocodingService().reverse_geocode(lat_f, lng_f)
                if area:
                    request.session['detected_area'] = area
            except Exception:
                pass
        try:
            request.session.modified = True
        except AttributeError:
            pass
        return JsonResponse({'success': True, 'message': 'Location saved', 'lat': lat, 'lng': lng})

    if pincode and re.match(r'^[1-9]\d{5}$', pincode):
        request.session['last_pincode'] = pincode
        for k in ['last_lat', 'last_lng', 'lat', 'lng', 'last_location', 'detected_area']:
            request.session.pop(k, None)
        loc = resolve_home_location(request)
        request.session['detected_area'] = loc.get('detected_area') or pincode
        if loc.get('user_lat') is not None and loc.get('user_lng') is not None:
            request.session['last_lat'] = str(loc['user_lat'])
            request.session['last_lng'] = str(loc['user_lng'])
        try:
            request.session.modified = True
        except AttributeError:
            pass
        return JsonResponse({
            'success': True,
            'message': 'Pincode saved',
            'pincode': pincode,
            'detected_area': request.session.get('detected_area', pincode),
            'city_label': loc.get('city_label') or pincode,
        })

    return JsonResponse({'success': False, 'message': 'No valid location data provided'}, status=400)




