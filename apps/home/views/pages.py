from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
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
from apps.agents.models import Agent, AgentPortfolio, AgentReview, City, FavoriteAgent
from apps.home.models import Pincode, PincodeCache
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
from django.db.models import Avg, Q
from django.db.models.expressions import RawSQL
from django.core.paginator import Paginator
from django.core.cache import cache

logger = logging.getLogger(__name__)


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


def terms(request):
    return render(request, 'public/terms.html')


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


@require_POST
def contact_submit(request):
    """
    AJAX contact form handler — mirrors Laravel's ContactController.store().
    Validates input, saves to contact_submissions table, returns JSON.
    """
    logger.info('CONTACT FORM SUBMISSION — received data: %s', request.POST.dict())

    try:
        name    = request.POST.get('name', '').strip()
        mobile  = request.POST.get('mobile', '').strip()
        email   = request.POST.get('email', '').strip()
        company = request.POST.get('company', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()

        # Validation
        errors = {}
        if len(name) < 2 or len(name) > 100:
            errors['name'] = ['Full name must be between 2 and 100 characters.']
        if not re.fullmatch(r'[0-9]{10}', mobile):
            errors['mobile'] = ['Please enter a valid 10-digit mobile number.']
        if not email or '@' not in email or len(email) > 100:
            errors['email'] = ['Please enter a valid email address.']
        if len(subject) < 5 or len(subject) > 100:
            errors['subject'] = ['Subject must be between 5 and 100 characters.']
        if len(message) < 10 or len(message) > 1000:
            errors['message'] = ['Message must be between 10 and 1000 characters.']

        if errors:
            return JsonResponse({
                'success': False,
                'message': 'Please fix the validation errors below.',
                'errors':  errors,
            }, status=422)

        # Save to DB
        submission = ContactSubmission.objects.create(
            name=name,
            mobile=mobile,
            email=email,
            company=company or None,
            subject=subject,
            message=message,
            status='pending',
        )
        logger.info('CONTACT FORM SUBMISSION — saved #%s ref=%s', submission.id, submission.reference_id)

        return JsonResponse({
            'success': True,
            'message': 'Thank you! Your message has been sent successfully. We will get back to you soon.',
        }, status=200)

    except Exception as exc:
        logger.error('CONTACT FORM SUBMISSION — Error: %s', exc, exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Failed to submit your message. Please try again.',
        }, status=400)


def _reviews_json_for_script(reviews):
    """Serialise testimonials for `var reviewsData = {{ reviews_json|safe }}`.

    The homepage JS concatenates these fields into innerHTML, and anonymous
    reviews are auto-approved, so every string is HTML-escaped here (safe in
    both text and quoted-attribute positions) — this was stored XSS on the
    public homepage. `</` is also neutralised so a value can never close the
    surrounding <script> element.
    """
    import html as _html

    safe_reviews = []
    for review in reviews or []:
        if not isinstance(review, dict):
            continue
        safe_reviews.append({
            key: _html.escape(value, quote=True) if isinstance(value, str) else value
            for key, value in review.items()
        })
    return json.dumps(safe_reviews).replace('</', '<\\/')


def _organization_schema(request):
    """Organization + WebSite JSON-LD for the homepage. Only verifiable fields:
    the footer phone/address defaults are placeholders, so they are left out."""
    from apps.agents.services.og_urls import get_public_site_base
    from apps.home.context_processors import footer_settings

    base = get_public_site_base(request)
    footer = footer_settings(request)['footer_settings']
    name = footer.get('site_name') or 'PadosiAgent'
    org = {
        '@type': 'Organization',
        '@id': f'{base}/#organization',
        'name': name,
        'url': f'{base}/',
        'logo': base + staticfiles_storage.url('img/padosi-agent-logo-new.png'),
        'description': 'Hyperlocal platform to find verified insurance agents near you in India.',
    }
    same_as = [u for u in footer.get('social_links', {}).values() if str(u).startswith('https://')]
    if same_as:
        org['sameAs'] = same_as
    return {
        '@context': 'https://schema.org',
        '@graph': [
            org,
            {
                '@type': 'WebSite',
                '@id': f'{base}/#website',
                'url': f'{base}/',
                'name': name,
                'publisher': {'@id': f'{base}/#organization'},
            },
        ],
    }


def home(request):
    cms = build_homepage_cms_context()
    settings = cms['settings']

    # Testimonials: admin custom list wins; otherwise approved reviews (cached).
    reviews = cms.get('custom_reviews') or []
    if not reviews:
        reviews = cache.get('homepage_reviews')
    if not reviews:
        from apps.agents.models import AgentReview
        db_reviews = AgentReview.objects.filter(is_approved=True).select_related('agent', 'agent__profile').order_by('-created_at')[:100]

        agent_counts = {}
        final_reviews = []
        backfill_reviews = []

        for rev in db_reviews:
            agent_id = rev.agent_id
            if agent_id:
                if agent_id not in agent_counts:
                    agent_counts[agent_id] = 0
                if agent_counts[agent_id] < 3:
                    final_reviews.append(rev)
                    agent_counts[agent_id] += 1
                else:
                    backfill_reviews.append(rev)
            else:
                final_reviews.append(rev)

        if len(final_reviews) < 10 and backfill_reviews:
            needed = 10 - len(final_reviews)
            final_reviews.extend(backfill_reviews[:needed])

        final_reviews = final_reviews[:10]

        reviews = []
        for rev in final_reviews:
            agent_name = rev.agent.fullname if rev.agent else None
            agent_slug = None
            agent_photo = None
            agent_state = 'gj' # Default fallback

            if rev.agent:
                try:
                    profile = rev.agent.get_primary_profile()
                    agent_slug = profile.slug
                    agent_photo = profile.profile_photo_url
                    agent_state = profile.state_code
                except Exception:
                    pass

            from urllib.parse import quote as _urlquote
            avatar_url = small_avatar_url(agent_photo) if (agent_photo and 'avatar-icon.jpg' not in agent_photo) else f"https://ui-avatars.com/api/?name={_urlquote(rev.reviewer_name or 'User')}&background=0d9488&color=fff&bold=true"

            reviews.append({
                'name': rev.reviewer_name or 'User',
                'service': f"Client of {agent_name}" if agent_name else "Verified Client",
                'agent_url': f"/{agent_state}/{agent_slug}/" if agent_slug else None,
                'rating': float(rev.rating),
                'comment': rev.review or '',
                'image': avatar_url
            })

        # No placeholder testimonials: unverifiable claims are a YMYL risk.
        # With zero approved reviews the template hides the section.
        if not cms.get('custom_reviews'):
            cache.set('homepage_reviews', reviews, 1800)

    chart_data = [
        {'year': '2020', 'rejection': 12},
        {'year': '2021', 'rejection': 16},
        {'year': '2022', 'rejection': 21},
        {'year': '2023', 'rejection': 27},
        {'year': '2024', 'rejection': 34},
    ]

    raw_heading = settings.hero_heading
    # Clean braces first if any
    cleaned_heading = raw_heading.replace('{', '').replace('}', '')
    def replace_word(match):
        word = match.group(0)
        lower_word = word.lower()
        if 'padosi' in lower_word:
            return f'<span class="pa-heading-highlight">{word}</span>'
        else:
            return f'<span class="pa-heading-trusted">{word}</span>'
    hero_heading_html = re.sub(r'\b(Trusted|Licensed|Licenced|Padosi|Agent)\b', replace_word, cleaned_heading, flags=re.IGNORECASE)

    return render(request, 'public/home.html', {
        'settings': settings,
        'why_cards_zipped': cms['why_cards_zipped'],
        'reviews_json': _reviews_json_for_script(reviews),
        'has_reviews': bool(reviews),
        'org_schema': _organization_schema(request),
        'hide_header': True,
        'trust_badges': cms['trust_badges'],
        'stats_data': cms['stats_data'],
        'product_tiles': cms['product_tiles'],
        'facts_zipped': cms['facts_zipped'],
        'slides_zipped': cms['slides_zipped'],
        'quick_picks': cms['quick_picks'],
        'why_cards': cms['why_cards'],
        'works_steps': cms['works_steps'],
        'chart_data': chart_data,
        'hero_heading_html': hero_heading_html,
    })


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

    company_set = {}
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


def fetch_filtered_agents_list(request):
    pincode = (request.GET.get('pincode') or request.session.get('last_pincode', '')).strip()
    location = (request.GET.get('location') or request.session.get('last_location', '')).strip()
    lat = (request.GET.get('lat') or request.session.get('last_lat', '')).strip()
    lng = (request.GET.get('lng') or request.session.get('last_lng', '')).strip()
    detected_area = request.GET.get('detected_area') or request.session.get('detected_area', '')

    service_type_input = request.GET.getlist('ServiceType')

    # Core query build — do not require auth_user; PHP-imported agents often have none.
    query = listed_agents_queryset()
    query = query.select_related('profile', 'performanceStats').prefetch_related(
        'insuranceSegments', 'reviews', 'serviceableCities', 'productExpertise', 'servicePincodes'
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
            request.session['detected_area'] = detected_area

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
        request.session['detected_area'] = detected_area

    if user_lat and user_lng:
        request.session['lat'] = str(user_lat)
        request.session['lng'] = str(user_lng)

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
        escaped = claim_company_input.replace('"', '\\"')
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
            request.session['last_pincode'] = pincode_param
            request.session.pop('last_location', None)
            detected_area = pincode_param
            
            # Resolve pincode to area name immediately (before redirect)
            if re.match(r'^[1-9]\d{5}$', pincode_param):
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
            
            request.session['detected_area'] = detected_area

        if location_param:
            request.session['last_location'] = location_param
            request.session['detected_area'] = location_param
            if not pincode_param:
                request.session.pop('last_pincode', None)

        # Clear old GPS memory
        for k in ['last_lat', 'last_lng', 'lat', 'lng']:
            if k in request.session:
                del request.session[k]

    elif lat_param and lng_param:
        request.session['last_lat'] = lat_param
        request.session['last_lng'] = lng_param
        
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
    service_type = service_type_input[0] if service_type_input else ''
    
    has_any_filter = bool(
        request.GET.get('ServiceType') or
        request.GET.get('InsuranceType') or
        request.GET.get('InsuranceCompany') or
        request.GET.get('ComplaintType') or
        request.GET.get('search')
    )

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
    if not invalid_pincode and agents_page:
        def _async_track_search(search_pincode, agent_ids):
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
            finally:
                from django.db import close_old_connections
                close_old_connections()

        try:
            import threading
            _tracked_agent_ids = [_a.id for _a in agents_page]
            threading.Thread(
                target=_async_track_search,
                args=(pincode or None, _tracked_agent_ids),
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


@require_GET
def pincode_fetch(request, pincode):
    if not re.match(r'^[1-9]\d{5}$', pincode):
        return JsonResponse({'success': False, 'message': 'Invalid pincode format.'})

    cache_key = f'pincode_fetch_json_{pincode}'
    cached_payload = cache.get(cache_key)
    if cached_payload is not None and isinstance(cached_payload, dict):
        data = cached_payload.get('data')
        if isinstance(data, dict) and not data.get('taluk'):
            data['taluk'] = data.get('district') or ''
        return JsonResponse(cached_payload)

    # Check exact curated pin first
    from apps.home.services.distance import DistanceService
    exact = DistanceService.get_precise_pincode_coordinates(pincode)
    if exact:
        formatted_location = f"{exact.get('office_name', '')}, {exact.get('district', '')}".strip(', ')
        payload = {
            'success': True,
            'data': {
                'office_name': exact.get('office_name') or f"PIN {pincode}",
                'district': exact.get('district') or '',
                'taluk': (exact.get('taluk') or exact.get('district') or '')[:100],
                'state': exact.get('state') or 'India',
                'formatted_location': formatted_location,
                'latitude': str(exact['lat']),
                'longitude': str(exact['lng']),
            }
        }
        cache.set(cache_key, payload, timeout=86400 * 7)
        # Ensure database is updated with exact curated metadata
        _get_or_create_pincode(pincode)
        return JsonResponse(payload)

    record = Pincode.objects.filter(pincode=pincode).first()
    if not record:
        record = _get_or_create_pincode(pincode)

    if not record:
        return JsonResponse({'success': False, 'message': 'Pincode not found.'})

    formatted_location = record.formatted_location
    
    # Try to enhance the location name using GeocodingService (mirrors PHP behavior)
    from apps.home.services.geocoding import GeocodingService
    geo_svc = GeocodingService()
    resolved = geo_svc.resolve_coordinates(pincode)
    
    if resolved and resolved.get('display_name'):
        formatted_location = resolved['display_name']
        # Optionally update the database record to cache this better name
        if record.office_name != formatted_location and not re.match(r'^(Area|Region)\s+\d', record.office_name, re.IGNORECASE):
            record.office_name = formatted_location
            record.district = ''
            record.save()

    payload = {
        'success': True,
        'data': {
            'office_name': record.office_name,
            'district': record.district,
            'taluk': (record.taluk or record.district or '')[:100],
            'state': record.state,
            'formatted_location': formatted_location,
            'latitude': str(record.latitude),
            'longitude': str(record.longitude),
        }
    }
    cache.set(cache_key, payload, timeout=86400 * 7)
    return JsonResponse(payload)


def _get_or_create_pincode(pincode):
    """Upserts the pincodes table from the postalpincode.in API (PincodeService::getOrCreatePincode)."""
    # 1. Exact curated coordinates take top precedence
    from apps.home.services.distance import DistanceService
    exact = DistanceService.get_precise_pincode_coordinates(pincode)
    if exact:
        try:
            record, _ = Pincode.objects.update_or_create(
                pincode=pincode,
                defaults={
                    'office_name': (exact.get('office_name') or f"PIN {pincode}")[:150],
                    'district': (exact.get('district') or '')[:100],
                    'state': (exact.get('state') or 'Gujarat')[:50],
                    'latitude': exact['lat'],
                    'longitude': exact['lng'],
                    'taluk': (exact.get('taluk') or '')[:100],
                }
            )
            return record
        except Exception as e:
            logger.warning(f"Error saving exact pincode {pincode}: {e}")

    existing = Pincode.objects.filter(pincode=pincode).first()
    if existing and existing.latitude and existing.longitude:
        return existing
    try:
        resp = http_requests.get(
            f'https://api.postalpincode.in/pincode/{pincode}',
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
            timeout=(2.0, 3.0)
        )
        resp.raise_for_status()
        body = resp.json()
        if not body or body[0].get('Status') != 'Success' or not body[0].get('PostOffice'):
            return None

        from apps.home.services.geocoding import GeocodingService
        post_offices = body[0]['PostOffice']
        po = GeocodingService._pick_best_post_office(post_offices) or post_offices[0]
        try:
            lat_val = po.get('Latitude')
            lng_val = po.get('Longitude')
            try:
                lat = float(lat_val) if lat_val and str(lat_val).lower() != 'na' else 0.0
                lng = float(lng_val) if lng_val and str(lng_val).lower() != 'na' else 0.0
            except ValueError:
                lat, lng = 0.0, 0.0

            taluk = po.get('Taluk') or po.get('Block') or ''
            record, _ = Pincode.objects.update_or_create(
                pincode=pincode,
                defaults={
                    'office_name': (po.get('Name') or '')[:150],
                    'district': (po.get('District') or '')[:100],
                    'state': (po.get('State') or '')[:50],
                    'latitude': lat,
                    'longitude': lng,
                    'division': (po.get('Division') or '')[:100],
                    'region': (po.get('Region') or '')[:100],
                    'circle': (po.get('Circle') or '')[:100],
                    'taluk': taluk[:100],
                }
            )
            return record
        except Exception as e:
            logger.error(f"Error saving pincode {pincode}: {e}")
            return None
    except Exception:
        return None


def _pincode_matching_agents(pincode):
    """Count/fetch agents servicing a pincode — mirrors HomeController@checkPincode:
    agents.agent_pincode match OR agent_profiles.service_pincodes JSON contains the pin
    OR agent_service_pincodes rows, restricted to registered statuses."""
    pin = str(pincode or '').strip()
    q = (
        Q(agent_pincode=pin)
        | Q(profile__service_pincodes__contains=pin)
        | Q(servicePincodes__service_pincode=pin)
    )
    if pin.isdigit():
        q |= Q(profile__service_pincodes__contains=int(pin))
    return Agent.objects.filter(
        status__in=['active', 'pending_manager_approval', 'pending_accounts_payment', 'pending_admin_approval']
    ).filter(q).distinct()


def check_pincode(request):
    """Public PIN-code competition checker — port of HomeController@checkPincode
    (route 'check.pincode', restrict.agent middleware → agents are redirected away)."""
    if request.user.is_authenticated:
        try:
            if Agent.objects.filter(user=request.user).exists():
                return redirect('agents:agent_dashboard')
        except Exception:
            pass

    pincode = (request.GET.get('pincode') or '').strip()
    results = None

    if pincode:
        if re.match(r'^[1-9]\d{5}$', pincode):
            details = _get_or_create_pincode(pincode)
            matching = _pincode_matching_agents(pincode)
            agents_count = matching.count()
            agents = matching.select_related('profile').prefetch_related('insuranceSegments')[:3]
            results = {
                'pincode': pincode,
                'details': details,
                'count': agents_count,
                'agents': agents,
                'invalid': False,
            }
        else:
            results = {'pincode': pincode, 'invalid': True}

    if request.headers.get('HX-Request') or request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'partials/pincode-check-results.html', {'results': results})

    return render(request, 'check-pincode.html', {'results': results})


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


def cancellation_refund_policy(request):
    """Cancellation & refund policy — port of routes/web.php:500-502 inline closure."""
    return render(request, 'public/cancellation-refund-policy.html')


def check_pincode_agents(request, pincode):
    """AJAX agent-count for a pincode — port of Api.PincodeController@checkAgents:
    GET /api/pincode/check-agents/{pincode} → {success, pincode, count}."""
    if not pincode or not pincode.isdigit() or len(pincode) != 6:
        return JsonResponse({'success': False, 'message': 'Invalid pincode format'}, status=400)
    
    cache_key = f'pincode_agent_count_{pincode}'
    count = cache.get(cache_key)
    if count is None:
        count = Agent.objects.filter(agent_pincode=pincode).count()
        cache.set(cache_key, count, timeout=60)
    return JsonResponse({'success': True, 'pincode': pincode, 'count': count})


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
    if AgentProfile.objects.filter(slug=slug).exists() or Agent.objects.filter(profile__slug=slug).exists():
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
        'irdai_verified': bool(profile.license_number) if profile else False,
        'amfi_verified': bool(profile.arn_number) if profile else False,
        'languages': profile.languages if (profile and profile.languages) else "N/A",
        'response_rate': resp_rate,
        'profile_completion': comp_score,
        'mobile': agent.mobile,
        'whatsapp': agent.whatsapp_raw,
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
            geo_svc = GeocodingService()
            area = geo_svc.reverse_geocode(float(lat), float(lng))
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



# ---------------------------------------------------------------------------
# Area/locality → pincodes mapping for major Indian cities.
# Used by city_agents_directory to resolve hyperlocal area slugs.
# ---------------------------------------------------------------------------
_AREA_PINCODE_MAP = {
    # Ahmedabad localities
    'paldi': ['380007'],
    'satellite': ['380015'],
    'bopal': ['380058'],
    'bodakdev': ['380054'],
    'vastrapur': ['380015'],
    'navrangpura': ['380009'],
    'sg highway': ['382481', '380059'],
    's g highway': ['382481', '380059'],
    'prahlad nagar': ['380015'],
    'thaltej': ['380059'],
    'maninagar': ['380008'],
    'vastral': ['382418'],
    'chandkheda': ['382424'],
    'gota': ['382481'],
    'nikol': ['382350'],
    'naranpura': ['380013'],
    'memnagar': ['380052'],
    'vejalpur': ['380051'],
    'juhapura': ['380055'],
    'isanpur': ['382443'],
    'odhav': ['382415'],
    'naroda': ['382330'],
    'motera': ['380005'],
    'sabarmati': ['380019'],
    'ranip': ['382480'],
    'science city': ['380060'],
    'shilaj': ['380058'],
    'shela': ['382213'],
    'ambli': ['380058'],
    'uvarsad': ['382422'],
    'sanand': ['382110'],
    'ghuma': ['380058'],
    'south bopal': ['380058'],
    'new ranip': ['382480'],
    'krishnanagar': ['382346'],
    'vatva': ['382445'],
    'rakhial': ['380023'],
    'ghodasar': ['380050'],
    'nikol-naroda': ['382350'],
    'new cg road': ['382421'],
    'chharodi': ['382481'],
    'tragad': ['382470'],
    'sola': ['380060'],
    'hebatpur': ['382422'],
    'dhandhuka': ['382460'],
    'dholka': ['382225'],
    'bavla': ['382220'],
    'dehgam': ['382305'],
    'unjha': ['384170'],
    'mehsana': ['384002'],
    'gandhinagar': ['382010', '382021', '382022', '382023', '382024', '382028'],
    'kudasan': ['382421'],
    'adalaj': ['382421'],
    'pethapur': ['382610'],
    # Surat localities
    'adajan': ['395009'],
    'athwa': ['395001'],
    'citylight': ['395007'],
    'vesu': ['395007'],
    'piplod': ['395007'],
    'althan': ['395017'],
    'pal': ['395009'],
    'katargam': ['395004'],
    'udhna': ['394210'],
    'varachha': ['395006'],
    'rander': ['395005'],
    'dumas': ['394550'],
    'sachin': ['394230'],
    'pandesara': ['394221'],
    'bhestan': ['395023'],
    'magdalla': ['395007'],
    'ghod dod road': ['395001'],
    'ghod-dod road': ['395001'],
    'laskana': ['394210'],
    # Rajkot localities
    'kalawad road': ['360005'],
    'gondal road': ['360002'],
    'mavdi': ['360004'],
    'raiya road': ['360007'],
    'university road': ['360005'],
    'bhaktinagar': ['360002'],
    'pedak road': ['360003'],
    'kothariya': ['360003'],
    'aji industrial': ['360003'],
    'metoda': ['360021'],
    # Vadodara localities
    'alkapuri': ['390007'],
    'fatehgunj': ['390002'],
    'productivity road': ['390020'],
    'harni': ['390022'],
    'gorwa': ['390016'],
    'makarpura': ['390014'],
    'karelibaug': ['390018'],
    'waghodia road': ['390019'],
    'subhanpura': ['390023'],
    'vasna': ['390007'],
    'manjalpur': ['390011'],
    'sama': ['390008'],
    # Mumbai localities
    'andheri': ['400058', '400053', '400069'],
    'bandra': ['400050', '400051'],
    'powai': ['400076'],
    'malad': ['400064', '400095'],
    'borivali': ['400066', '400091', '400092'],
    'kandivali': ['400067', '400101'],
    'goregaon': ['400062', '400063'],
    'jogeshwari': ['400060'],
    'vile parle': ['400056', '400057'],
    'santacruz': ['400054', '400055'],
    'kurla': ['400070', '400024'],
    'ghatkopar': ['400077', '400086'],
    'mulund': ['400080', '400081'],
    'thane': ['400601', '400602', '400603'],
    'navi mumbai': ['400614', '400703', '400705'],
    # Bangalore localities
    'koramangala': ['560034'],
    'indiranagar': ['560038'],
    'whitefield': ['560066'],
    'hsr layout': ['560102'],
    'marathahalli': ['560037'],
    'electronic city': ['560100'],
    'jp nagar': ['560078'],
    'jayanagar': ['560041'],
    'btm layout': ['560076'],
    'yelahanka': ['560064'],
    # Pune localities
    'baner': ['411045'],
    'kothrud': ['411038'],
    'viman nagar': ['411014'],
    'hinjewadi': ['411057'],
    'wakad': ['411057'],
    'kharadi': ['411014'],
    'hadapsar': ['411028'],
    'aundh': ['411007'],
    'deccan': ['411004'],
    'pimpri chinchwad': ['411017', '411018', '411019'],
}


MIN_INDEXABLE_CITY_AGENTS = 1
# Agent-typed "cities" that are not places: pages stay up (profile breadcrumbs link here) but are noindex and kept out of the sitemap.
JUNK_CITY_SLUGS = frozenset({'all-pune', 'all-world', 'and-all-over-world', 'pan-india'})


def _resolve_area_to_pincodes(area_name_lower):
    """Return a list of pincodes for a known locality/area name, else empty list."""
    area = area_name_lower.strip()
    if area in _AREA_PINCODE_MAP:
        return _AREA_PINCODE_MAP[area]
    # Partial match: check if any key starts with / contains the area
    for key, pins in _AREA_PINCODE_MAP.items():
        if area in key or key in area:
            return pins
    return []


# /insurance-agents/<city>/<category>/ pages: slug → segment_type in insuranceSegments.
CITY_CATEGORIES = {
    'health-insurance': {
        'label': 'Health Insurance',
        'segment': 'health',
        'keywords': 'health insurance agent in {city}, mediclaim agent in {city}, health insurance advisor near me {city}, family floater health insurance {city}',
        'intro': (
            'Find verified health insurance and mediclaim agents in {city}. A local advisor helps you compare '
            'family floater, senior citizen and top-up plans, checks which network hospitals in {city} offer '
            'cashless treatment, and stays by your side when you file a claim.'
        ),
        'faqs': [
            ('Does buying health insurance through an agent in {city} cost more?',
             'No. The premium is fixed by the insurance company and is the same whether you buy online or through '
             'an agent. The agent is paid by the insurer, not by you.'),
            ('Can a local agent help with a cashless claim at a hospital in {city}?',
             'Yes. An agent can tell you which hospitals are in your insurer\'s cashless network, help with the '
             'pre-authorisation form and follow up with the insurer or TPA. Final approval is given by the insurer.'),
            ('What should I check before choosing a health insurance plan?',
             'Check the sum insured, waiting periods for pre-existing diseases, room rent limits, co-payment, '
             'the insurer\'s network hospitals near you and its claim settlement record.'),
            ('How do I contact a health insurance agent on PadosiAgent?',
             'Open any agent profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
    'life-insurance': {
        'label': 'Life Insurance',
        'segment': 'life',
        'keywords': 'life insurance agent in {city}, LIC agent in {city}, LIC agent near me {city}, term insurance advisor {city}',
        'intro': (
            'Find verified life insurance, term insurance and LIC agents in {city}. A local advisor helps you '
            'work out the cover your family needs, compare term, endowment and retirement plans, and supports '
            'your nominee when it is time to claim.'
        ),
        'faqs': [
            ('How do I find a trusted LIC or life insurance agent in {city}?',
             'Compare the verified agents on this page by experience, reviews and the companies they represent, '
             'then call or WhatsApp them directly from their profile.'),
            ('Is term insurance better than an endowment or money-back plan?',
             'Term insurance gives the highest cover for the lowest premium but pays only on death. Endowment and '
             'money-back plans add savings but cost more for the same cover. An agent can help you choose based on your goals.'),
            ('How much life cover should I take?',
             'A common rule of thumb is 10 to 15 times your yearly income, plus any loans. Your agent can work out '
             'a figure based on your family\'s expenses and goals.'),
            ('Does a life insurance agent help my family with the claim?',
             'Yes. A local agent helps the nominee collect documents, fill the claim form and follow up with the insurer.'),
        ],
    },
    'lic-agents': {
        'label': 'LIC',
        # Matched on the insurer name saved in the agent's portfolio (see fastapi_app/utils/companies.py).
        'companies': ['Life Insurance Corporation'],
        'keywords': 'LIC agent in {city}, LIC agent near me {city}, LIC policy advisor {city}, LIC premium payment help {city}, LIC claim assistance {city}',
        'intro': (
            'Find verified LIC agents in {city}. A local LIC advisor helps you choose between term, endowment, '
            'money-back and pension plans, keeps track of premium due dates, revives lapsed policies and supports '
            'your family with maturity and death claims.'
        ),
        'faqs': [
            ('How do I find a genuine LIC agent in {city}?',
             'Every agent on this page represents LIC on their PadosiAgent profile. Check their experience and reviews, '
             'and ask for their LIC agent code before you buy.'),
            ('Can an LIC agent help me revive a lapsed policy?',
             'Yes. An agent can tell you the revival amount, any medical requirements and the forms LIC needs.'),
            ('Does an LIC agent help with maturity and death claims?',
             'Yes. The agent helps you or your nominee collect the documents, submit the claim to the LIC branch and follow it up.'),
            ('Is it free to contact an LIC agent on PadosiAgent?',
             'Yes. Open any agent profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
    'motor-insurance': {
        'label': 'Car & Bike Insurance',
        'segment': 'motor',
        'keywords': 'car insurance agent in {city}, bike insurance agent in {city}, motor insurance renewal {city}, two wheeler insurance agent near me {city}',
        'intro': (
            'Find verified car and bike insurance agents in {city}. A local advisor helps you renew on time, '
            'pick the right add-ons like zero depreciation, transfer your no-claim bonus and handle the survey '
            'and garage paperwork after an accident.'
        ),
        'faqs': [
            ('Can an agent in {city} renew my expired car or bike insurance?',
             'Yes. If the policy has lapsed the insurer may ask for a vehicle inspection before renewal. A local agent can arrange it.'),
            ('Is third-party insurance enough for my vehicle?',
             'Third-party cover is the legal minimum, but it does not pay for damage to your own vehicle. A '
             'comprehensive policy covers both.'),
            ('What documents do I need for a car insurance claim after an accident?',
             'Usually the policy copy, RC, driving licence, claim form, repair estimate and, for theft or major '
             'accidents, an FIR. Your agent will confirm what your insurer needs.'),
            ('Will I lose my no-claim bonus if I switch insurers?',
             'No. The no-claim bonus belongs to you, not the insurer, and can be transferred when you renew with another company.'),
        ],
    },
    'business-insurance': {
        'label': 'Business Insurance',
        'segment': 'sme',
        'keywords': 'business insurance agent in {city}, SME insurance advisor {city}, shop insurance {city}, group health insurance for employees {city}, fire insurance agent {city}',
        'intro': (
            'Find verified business and SME insurance advisors in {city}. A local advisor helps shops, factories '
            'and offices choose fire, property, liability, cyber and employee group health cover that fits the business.'
        ),
        'faqs': [
            ('What insurance does a small business in {city} need?',
             'Most businesses start with fire and property cover for the premises and stock, plus group health '
             'cover for employees. Liability and cyber cover depend on the type of business.'),
            ('Can an agent arrange group health insurance for my employees?',
             'Yes. Group health (GMC) and group personal accident (GPA) policies can be arranged for teams of any size.'),
            ('Does a business insurance agent help with claims?',
             'Yes. The agent helps with the claim intimation, surveyor visit and documents, and follows up with the insurer.'),
            ('How do I contact a business insurance advisor on PadosiAgent?',
             'Open any advisor profile on this page and call or WhatsApp them directly. There is no fee for using PadosiAgent.'),
        ],
    },
}


# /<service>/<city>/ pages: every listed agent in the city, with service-specific copy.
SERVICE_PAGES = {
    'insurance-claim-assistance': {
        'label': 'Insurance Claim Assistance',
        'keywords': 'insurance claim assistance in {city}, insurance claim support {city}, health insurance claim assistance {city}, car insurance claim assistance {city}, insurance claim advisor near me {city}',
        'intro': (
            'Get help with your insurance claim in {city}. Verified local advisors guide you through health, '
            'life, motor and business insurance claims: what to tell the insurer, which documents to collect, '
            'cashless versus reimbursement, and how to follow up on a delayed or rejected claim.'
        ),
        'faqs': [
            ('Can a local advisor in {city} help if my policy was bought from someone else?',
             'Yes. Many advisors on this page help with claims on any policy. Share your policy details when you '
             'contact them and they will tell you how they can help.'),
            ('What documents are usually needed for a health insurance claim?',
             'Usually the claim form, policy copy, ID proof, hospital bills, discharge summary, doctor\'s '
             'prescriptions and test reports. For reimbursement claims you also need the original bills and a '
             'cancelled cheque. Your insurer may ask for more.'),
            ('What should I do first after a car accident?',
             'Inform your insurer as soon as you can, take photos of the vehicle and the spot, and do not move the '
             'vehicle to a garage before the insurer says so. File an FIR if there is injury, theft or major damage.'),
            ('My claim was rejected. Can an advisor help?',
             'An advisor can read the rejection letter, check it against your policy terms and help you appeal to '
             'the insurer\'s grievance cell. If that fails, you can approach the Insurance Ombudsman.'),
        ],
    },
    'insurance-renewal': {
        'label': 'Insurance Policy Renewal',
        'keywords': 'insurance policy renewal agent {city}, insurance renewal near me {city}, health insurance renewal agent {city}, car insurance renewal {city}, bike insurance renewal agent {city}, insurance policy review {city}',
        'intro': (
            'Renew your health, life, car or bike insurance with a verified local advisor in {city}. An advisor '
            'reviews your current cover before renewal, compares plans, keeps your no-claim bonus and waiting-period '
            'benefits, and reminds you before the next due date.'
        ),
        'faqs': [
            ('What happens if I miss my health insurance renewal date?',
             'Most insurers give a short grace period. If you renew after it ends, the policy may lapse and you can '
             'lose waiting-period credit for pre-existing diseases. Renew before the due date.'),
            ('Can I switch insurers at renewal without losing benefits?',
             'Yes. Health insurance portability lets you carry waiting-period credit to a new insurer, and the motor '
             'no-claim bonus can be transferred. Apply before your current policy expires.'),
            ('Can my bike or car insurance be renewed after it has expired?',
             'Yes, but the insurer may ask for a vehicle inspection, and driving without valid insurance is illegal. '
             'A local advisor can arrange the inspection.'),
            ('Is a policy review before renewal useful?',
             'Yes. Your income, family and vehicle may have changed. A review checks whether your sum insured and '
             'add-ons still fit before you pay the next premium.'),
        ],
    },
}

# /insurance-agents/<state>/ hubs: every listed agent serving a city in that state.
# Live cities mostly have an empty `state`, so a hub also matches known city names and the agent's pincode.
STATE_HUBS = {
    'gujarat': {
        'name': 'Gujarat',
        'pin_prefixes': ('36', '37', '38', '39'),
        'cities': (
            'Ahmedabad', 'Surat', 'Vadodara', 'Rajkot', 'Gandhinagar', 'Bhavnagar', 'Jamnagar', 'Junagadh',
            'Anand', 'Nadiad', 'Bharuch', 'Ankleshwar', 'Navsari', 'Valsad', 'Vapi', 'Mehsana', 'Morbi',
            'Gandhidham', 'Bhuj', 'Porbandar', 'Amreli', 'Surendranagar', 'Palanpur', 'Patan', 'Himmatnagar',
            'Godhra', 'Dahod', 'Botad', 'Veraval', 'Kalol',
        ),
    },
}


def _state_city_q(hub, prefix=''):
    q = Q(**{f'{prefix}state__iexact': hub['name']})
    for name in hub['cities']:
        q |= Q(**{f'{prefix}name__iexact': name})
    return q


def state_hub_agents(agents_qs, hub):
    """Agents serving a city in the state, or whose own pincode is in the state."""
    q = _state_city_q(hub, 'serviceableCities__')
    for prefix in hub['pin_prefixes']:
        q |= Q(agent_pincode__startswith=prefix)
    return agents_qs.filter(q).distinct()


def filter_agents_for_category(agents_qs, category):
    """Narrow an agent queryset to a CITY_CATEGORIES / SERVICE_PAGES entry (services keep everyone)."""
    if category.get('segment'):
        agents_qs = agents_qs.filter(insuranceSegments__segment_type=category['segment']).distinct()
    if category.get('companies'):
        company_q = Q()
        for name in category['companies']:
            company_q |= Q(portfolios__primary_companies__icontains=name)
            company_q |= Q(portfolios__secondary_companies__icontains=name)
        agents_qs = agents_qs.filter(company_q).distinct()
    return agents_qs


def _directory_path(place_slug, key=None):
    if key in SERVICE_PAGES:
        return f"/{key}/{place_slug}/"
    if key:
        return f"/insurance-agents/{place_slug}/{key}/"
    return f"/insurance-agents/{place_slug}/"


def city_agents_directory(request, city_slug, category_slug=None, service_slug=None):
    """
    Programmatic Local SEO Hub: /insurance-agents/<city_slug>/
    Targeting 'insurance agent in <city>', 'best insurance agent in <city>'.

    Multi-tier resolution:
      1. Exact City model match → filter by serviceableCities (M2M)
      2. Known locality/area → filter by servicePincodes / address
      3. Text search on address / agent_pincode fields
      4. City-wide fallback using parent city name
    """
    from apps.agents.models import City
    from django.db.models import Q

    category = None
    if category_slug is not None:
        category = CITY_CATEGORIES.get(str(category_slug).lower())
        if not category:
            from django.http import Http404
            raise Http404("Category not found")
        category_slug = str(category_slug).lower()
    elif service_slug is not None:
        category = SERVICE_PAGES[service_slug]
        category_slug = service_slug

    raw_slug = str(city_slug).strip().lower()
    state_hub = STATE_HUBS.get(raw_slug)
    city_query_name = raw_slug.replace('-', ' ')

    # --- Tier 1: Try exact City model match ---
    city_obj = (
        City.objects.filter(slug=raw_slug).first()
        or City.objects.filter(name__iexact=city_query_name).first()
    )

    area_pincodes = []
    if state_hub:
        city_display = state_hub['name']
        state_display = 'India'
        agents_qs = state_hub_agents(listed_agents_queryset(), state_hub)
    elif city_obj:
        city_display = city_obj.name
        state_display = city_obj.state or 'Gujarat'

        # Use listed_agents_queryset() so PHP-imported agents are included
        base_qs = listed_agents_queryset()
        agents_qs = base_qs.filter(serviceableCities=city_obj).distinct()

        # If very few results, broaden to address/pincode text match as well
        if agents_qs.count() < 5:
            text_q = (
                Q(profile__address__icontains=city_display)
                | Q(profile__office_address__icontains=city_display)
                | Q(serviceableCities__name__icontains=city_display)
            )
            agents_qs = base_qs.filter(text_q).distinct()
    else:
        # --- Tier 2: Check locality/area dictionary ---
        area_pincodes = _resolve_area_to_pincodes(city_query_name)

        # Guess a "parent city" display name from the slug
        # e.g. 'paldi-ahmedabad' → 'Ahmedabad', 'satellite' → 'Satellite'
        parts = city_query_name.split()
        city_display = city_query_name.title()
        state_display = 'India'

        # Detect parent city name in slug parts (common city names)
        _KNOWN_CITIES = {
            'ahmedabad', 'surat', 'rajkot', 'vadodara', 'gandhinagar',
            'mumbai', 'delhi', 'bangalore', 'bengaluru', 'pune', 'hyderabad',
            'chennai', 'kolkata', 'jaipur', 'lucknow', 'indore',
        }
        parent_city_name = None
        for part in parts:
            if part in _KNOWN_CITIES:
                parent_city_name = part.title()
                break

        # For state we can set Gujarat for known Gujarat localities
        _GUJARAT_AREAS = set()
        for _key in _AREA_PINCODE_MAP:
            if any(p.startswith('3') for p in _AREA_PINCODE_MAP[_key]):
                _GUJARAT_AREAS.add(_key)
        if city_query_name in _GUJARAT_AREAS or (parent_city_name and parent_city_name.lower() in {
            'ahmedabad', 'surat', 'rajkot', 'vadodara', 'gandhinagar'
        }):
            state_display = 'Gujarat'

        base_qs = listed_agents_queryset()

        if area_pincodes:
            # Tier 2a: Match agents whose agent_pincode or service_pincodes overlaps
            pin_q = Q()
            for pin in area_pincodes:
                pin_q |= Q(agent_pincode__icontains=pin)
                pin_q |= Q(profile__address__icontains=pin)
                pin_q |= Q(servicePincodes__service_pincode=pin)

            # Also include area name in address
            pin_q |= Q(profile__address__icontains=city_query_name)
            pin_q |= Q(profile__office_address__icontains=city_query_name)

            agents_qs = base_qs.filter(pin_q).distinct()

            # If still sparse, add the parent city agents too
            if agents_qs.count() < 3 and parent_city_name:
                parent_city_obj = City.objects.filter(name__iexact=parent_city_name).first()
                if parent_city_obj:
                    city_qs = base_qs.filter(serviceableCities=parent_city_obj).distinct()
                    agents_qs = (agents_qs | city_qs).distinct()
        else:
            # --- Tier 3: Pure text search on address/city fields ---
            tokens = [t.strip() for t in city_query_name.split() if len(t.strip()) >= 3]
            text_q = Q()
            for token in tokens:
                text_q |= Q(profile__address__icontains=token)
                text_q |= Q(profile__office_address__icontains=token)
                text_q |= Q(serviceableCities__name__icontains=token)
                text_q |= Q(agent_pincode__icontains=token)

            agents_qs = base_qs.filter(text_q).distinct()

            # --- Tier 4: Fallback to any agent if nothing found ---
            if not agents_qs.exists() and parent_city_name:
                parent_city_obj = City.objects.filter(name__iexact=parent_city_name).first()
                if parent_city_obj:
                    agents_qs = base_qs.filter(serviceableCities=parent_city_obj).distinct()

    if category:
        agents_qs = filter_agents_for_category(agents_qs, category)

    agents_list = list(
        agents_qs
        .order_by('-created_at')[:200]   # cap to avoid full-table scans
    )
    # Unknown slug with no agents: a real 404, not an indexable "Agents in <anything>" page.
    if not agents_list and not city_obj and not area_pincodes and not state_hub:
        from django.http import Http404
        raise Http404("City not found")

    # Sort by rating descending
    agents_list.sort(key=lambda a: (getattr(a, 'average_rating', 0) or 0), reverse=True)

    # ---- Pagination: 12 cards per page ----
    from django.core.paginator import Paginator, InvalidPage
    paginator = Paginator(agents_list, 12)
    page_num = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_num)
    except InvalidPage:
        page_obj = paginator.page(1)

    # Nearby / active cities for internal linking footer
    top_cities = list(
        City.objects.filter(is_active=True, agents__status='active')
        .exclude(slug=raw_slug)
        .exclude(slug__in=JUNK_CITY_SLUGS)
        .exclude(name__iexact=city_display)
        .distinct()[:15]
    )

    state_cities = []
    if state_hub:
        from django.db.models import Count
        state_cities = [
            (_directory_path(c.slug, category_slug), c.name, c.n)
            for c in City.objects.filter(_state_city_q(state_hub), is_active=True,
                                         agents__in=listed_agents_queryset().values('id'))
            .annotate(n=Count('agents', distinct=True)).order_by('-n', 'name')[:40]
            if c.slug
        ]

    canonical_url = request.build_absolute_uri(f"/insurance-agents/{raw_slug}/")
    if page_obj.number > 1:
        # Paginated pages are self-canonical (Google ignores rel=prev/next).
        canonical_url += f"?page={page_obj.number}"
    # Empty pages (no agents) stay reachable but out of the index (soft-404 risk).
    meta_robots = 'index, follow' if paginator.count >= MIN_INDEXABLE_CITY_AGENTS and raw_slug not in JUNK_CITY_SLUGS else 'noindex, follow'
    meta_title = f"Verified Insurance Agents in {city_display} | Licensed Advisors — PadosiAgent"
    meta_desc = f"Looking for trusted insurance agents in {city_display}? Find verified local advisors for Health, Life, Car & Bike insurance with ratings & doorstep assistance on PadosiAgent."
    meta_kw = f"insurance agent in {city_display}, best insurance agent in {city_display}, insurance agent near me {city_display}, licensed insurance agent {city_display}, health insurance agent {city_display}, life insurance agent {city_display}, PadosiAgent"

    breadcrumb = [
        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': request.build_absolute_uri('/')},
        {'@type': 'ListItem', 'position': 2, 'name': 'Insurance Agents', 'item': request.build_absolute_uri('/find-agents/')},
        {'@type': 'ListItem', 'position': 3, 'name': city_display,
         'item': request.build_absolute_uri(f"/insurance-agents/{raw_slug}/")},
    ]
    if category:
        breadcrumb.append({'@type': 'ListItem', 'position': 4, 'name': f"{category['label']} Agents",
                           'item': request.build_absolute_uri(_directory_path(raw_slug, category_slug))})
    breadcrumb_schema = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': breadcrumb}

    category_context = {}
    if category:
        label = category['label']
        canonical_url = canonical_url.replace(f"/insurance-agents/{raw_slug}/", _directory_path(raw_slug, category_slug), 1)
        meta_title = f"{label} Agents in {city_display} - Verified Local Advisors | PadosiAgent"
        count_text = f"{paginator.count}+ " if paginator.count else ''
        meta_desc = (f"Looking for a trusted {label if label.isupper() else label.lower()} agent in {city_display}? Compare {count_text}verified local "
                     f"advisors with ratings and reviews. Connect directly on call or WhatsApp for free claim guidance.")
        meta_kw = category['keywords'].format(city=city_display) + ', PadosiAgent'
        faqs = [(q.format(city=city_display), a.format(city=city_display)) for q, a in category['faqs']]
        category_context = {
            'category': category,
            'category_slug': category_slug,
            'category_intro': category['intro'].format(city=city_display),
            'faqs': faqs,
            'faq_schema': {
                '@context': 'https://schema.org',
                '@type': 'FAQPage',
                'mainEntity': [
                    {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}}
                    for q, a in faqs
                ],
            },
        }

    context = {
        **category_context,
        'breadcrumb_schema': breadcrumb_schema,
        'city_categories': [(_directory_path(raw_slug, slug), c['label'])
                            for slug, c in {**CITY_CATEGORIES, **SERVICE_PAGES}.items() if slug != category_slug],
        'state_cities': state_cities,
        'city_name': city_display,
        'state_name': state_display,
        'city_slug': raw_slug,
        'agents': page_obj.object_list,
        'agent_count': paginator.count,
        'page_obj': page_obj,
        'paginator': paginator,
        'top_cities': top_cities,
        'canonical_url': canonical_url,
        'meta_title': meta_title,
        'meta_description': meta_desc,
        'meta_keywords': meta_kw,
        'meta_robots': meta_robots,
    }
    return render(request, 'public/city_directory.html', context)


@require_POST
def quick_lead_capture(request):
    """Handle instant lead inquiries submitted via the exit-intent popup."""
    name = request.POST.get('name', '').strip()
    mobile = request.POST.get('mobile', '').strip()
    pincode = request.POST.get('pincode', '').strip()
    insurance_type = request.POST.get('insurance_type', 'General').strip()

    if not name or not mobile:
        return JsonResponse({'status': 'error', 'message': 'Name and mobile number are required.'}, status=400)

    clean_mobile = re.sub(r'[^0-9]', '', mobile)
    if len(clean_mobile) < 10:
        return JsonResponse({'status': 'error', 'message': 'Please enter a valid 10-digit mobile number.'}, status=400)

    email = request.POST.get('email', '').strip() or f"lead_{clean_mobile}@padosiagent.com"
    subject = f"Exit Popup Lead: {insurance_type}"[:100]
    message = f"Customer Name: {name}\nMobile: {mobile}\nPincode: {pincode}\nInsurance Type: {insurance_type}\nSource: Exit-Intent Popup"

    try:
        ContactSubmission.objects.create(
            name=name[:100],
            email=email,
            mobile=clean_mobile[:10],
            subject=subject,
            message=message,
            status='pending'
        )
        return JsonResponse({
            'status': 'success',
            'message': 'Thank you! A verified neighbourhood advisor will connect with you shortly.'
        })
    except Exception as e:
        logger.error("Error creating exit popup lead: %s", e)
        return JsonResponse({'status': 'error', 'message': 'Could not submit your request. Please try again.'}, status=500)




