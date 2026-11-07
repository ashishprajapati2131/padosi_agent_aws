import json
import logging
import re
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Q
from django.views.decorators.http import require_http_methods

from apps.admin_panel.services import find_agent_locator_service
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.agents.models import Agent
from apps.home.models import Pincode, PincodeCache
from apps.home.services.geocoding import GeocodingService
from apps.home.services.distance import (
    DistanceService,
    iter_agent_service_pincodes,
    agent_serves_pincode,
    NEARBY_RADIUS_KM,
)

logger = logging.getLogger(__name__)

_PIN_RE = re.compile(r'^[1-9]\d{5}$')


def _check_admin(request):
    admin_id = _get_admin_from_session(request)
    return admin_id


def locator_index(request):
    """Render the Pincode Lat/Long Extractor & Find Agent Locator dashboard."""
    if not _check_admin(request):
        return redirect('admin_login_page')

    pincode_query = request.GET.get('pincode', '').strip()
    total_pincodes = Pincode.objects.count()
    total_active_agents = Agent.objects.filter(status='active').count()
    geocoded_agents = Agent.objects.filter(status='active', latitude__isnull=False, longitude__isnull=False).count()

    context = {
        'initial_pincode': pincode_query,
        'total_pincodes': total_pincodes,
        'total_active_agents': total_active_agents,
        'geocoded_agents': geocoded_agents,
    }
    return render(request, 'admin/find_agent_locator.html', context)


@require_http_methods(['GET', 'POST'])
def extract_coordinates(request):
    """
    Extract latitude, longitude, and locality details for any 6-digit Indian pincode.
    Multi-stage resolution:
      1. Local DB (Pincode model)
      2. PincodeCache
      3. GeocodingService (postal API + Nominatim OpenStreetMap)
      4. Regional fallback coordinates
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            pincode = str(data.get('pincode', '')).strip()
        except Exception:
            pincode = str(request.POST.get('pincode', '')).strip()
    else:
        pincode = str(request.GET.get('pincode', '')).strip()

    if not pincode:
        return JsonResponse({'success': False, 'message': 'Pincode is required.'}, status=400)

    if not _PIN_RE.match(pincode):
        return JsonResponse({
            'success': False,
            'message': 'Invalid Indian pincode format. Must be exactly 6 digits without starting with 0.'
        }, status=422)

    result = {
        'pincode': pincode,
        'latitude': None,
        'longitude': None,
        'office_name': '',
        'district': '',
        'state': '',
        'division': '',
        'taluk': '',
        'formatted_location': '',
        'source': 'Unknown',
        'is_in_database': False,
        'matching_agents_count': 0,
    }

    # Step 1: Check Exact Curated Pincodes first (highest priority)
    exact = DistanceService.get_precise_pincode_coordinates(pincode)
    if exact:
        result['latitude'] = float(exact['lat'])
        result['longitude'] = float(exact['lng'])
        result['office_name'] = exact.get('office_name') or f"PIN {pincode}"
        result['district'] = exact.get('district') or ''
        result['state'] = exact.get('state') or 'India'
        result['division'] = exact.get('division') or ''
        result['taluk'] = exact.get('taluk') or ''
        result['formatted_location'] = f"{result['office_name']}, {result['district']}".strip(', ')
        result['is_in_database'] = True
        result['source'] = 'Database (Master Records)'

        # Auto-sync to DB & cache so the whole platform is immediately updated
        try:
            PincodeCache.store_coordinates(
                pincode, result['latitude'], result['longitude'], result['formatted_location']
            )
            Pincode.objects.update_or_create(
                pincode=pincode,
                defaults={
                    'office_name': result['office_name'],
                    'district': result['district'],
                    'state': result['state'],
                    'latitude': Decimal(str(round(result['latitude'], 8))),
                    'longitude': Decimal(str(round(result['longitude'], 8))),
                    'taluk': result['taluk'],
                }
            )
        except Exception as e:
            logger.warning(f"[FindAgentLocator] Exact pin auto-sync failed: {e}")

    # Step 2: Check Local Master DB (if not already resolved by exact curated pins)
    if not result['latitude']:
        try:
            db_pin = Pincode.objects.filter(pincode=pincode).first()
            if db_pin and db_pin.latitude and db_pin.longitude:
                is_fallback = DistanceService.is_regional_fallback_coordinate(
                    pincode, db_pin.latitude, db_pin.longitude
                )
                result['latitude'] = float(db_pin.latitude)
                result['longitude'] = float(db_pin.longitude)
                result['office_name'] = db_pin.office_name or ''
                result['district'] = db_pin.district or ''
                result['state'] = db_pin.state or ''
                result['division'] = db_pin.division or ''
                result['taluk'] = db_pin.taluk or ''
                result['formatted_location'] = db_pin.formatted_location or f"{db_pin.office_name}, {db_pin.district}"
                result['is_in_database'] = True
                result['source'] = 'Database (Master Records)' if not is_fallback else 'Database (Regional Fallback)'
        except Exception as e:
            logger.warning(f"[FindAgentLocator] Pincode DB check failed: {e}")

    # Step 3: Check GeocodingService if DB is missing or coordinates are regional fallback
    if not result['latitude'] or 'Regional Fallback' in result.get('source', ''):
        try:
            geo_svc = GeocodingService()
            coords = geo_svc.resolve_coordinates(pincode)
            if coords and coords.get('lat') and coords.get('lng'):
                result['latitude'] = float(coords['lat'])
                result['longitude'] = float(coords['lng'])
                display_name = coords.get('display_name') or ''
                if not result['formatted_location']:
                    result['formatted_location'] = display_name
                if not result['office_name']:
                    # Extract office/locality from display_name
                    parts = [p.strip() for p in display_name.split(',') if p.strip()]
                    result['office_name'] = parts[0] if parts else f"PIN {pincode}"
                    if len(parts) > 1 and not result['district']:
                        result['district'] = parts[1]
                    if len(parts) > 2 and not result['state']:
                        result['state'] = parts[2]
                result['source'] = 'Geocoded (API / OpenStreetMap)'
        except Exception as e:
            logger.warning(f"[FindAgentLocator] GeocodingService lookup failed: {e}")

    # Step 4: Regional fallback as last resort
    if not result['latitude']:
        fallback = DistanceService.get_regional_fallback_coordinates(pincode)
        if fallback:
            result['latitude'] = float(fallback['lat'])
            result['longitude'] = float(fallback['lng'])
            result['source'] = 'Regional Fallback'
            if not result['formatted_location']:
                result['formatted_location'] = f"Area near {pincode}"

    if not result['latitude'] or not result['longitude']:
        return JsonResponse({
            'success': False,
            'message': f"Could not determine coordinates for pincode {pincode}. You can enter them manually."
        }, status=404)

    # Count how many agents currently serve or are near this pincode
    agents_count = _count_matching_agents(pincode, result['latitude'], result['longitude'])
    result['matching_agents_count'] = agents_count

    return JsonResponse({
        'success': True,
        'data': result,
    })


@require_http_methods(['POST'])
def save_pincode_to_master(request):
    """
    Save or update this pincode and its latitude/longitude in the Pincode master table
    and PincodeCache so the public Find Agent search recognizes it permanently.
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    pincode = str(data.get('pincode', '')).strip()
    office_name = str(data.get('office_name', '')).strip()
    district = str(data.get('district', '')).strip()
    state = str(data.get('state', '')).strip()
    division = str(data.get('division', '')).strip() or None
    taluk = str(data.get('taluk', '')).strip() or None

    try:
        lat_val = data.get('latitude') if data.get('latitude') is not None else data.get('lat')
        lng_val = data.get('longitude') if data.get('longitude') is not None else data.get('lng')
        lat = float(lat_val)
        lng = float(lng_val)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Valid numeric latitude and longitude are required.'}, status=422)

    if not _PIN_RE.match(pincode):
        return JsonResponse({'success': False, 'message': 'Invalid 6-digit pincode format.'}, status=422)

    if not office_name:
        office_name = district or f"Area {pincode}"
    if not district:
        district = office_name
    if not state:
        state = "India"

    try:
        created = find_agent_locator_service.save_pincode_to_master(
            pincode, lat, lng, office_name, district, state, division, taluk,
        )

        logger.info(f"[FindAgentLocator] Pincode {pincode} saved: lat={lat}, lng={lng}, created={created}")

        return JsonResponse({
            'success': True,
            'message': f"Pincode {pincode} ({office_name}) successfully {'saved to' if created else 'updated in'} Master Database.",
            'created': created,
        })
    except Exception as e:
        logger.error(f"[FindAgentLocator] Failed saving pincode to master: {e}")
        logger.exception("Admin request failed in find_agent_locator")  # detail stays server-side
        return JsonResponse({'success': False, 'message': "Database error. Details are in the server log."}, status=500)


@require_http_methods(['GET'])
def search_agents(request):
    """
    Search existing agents by name, email, mobile, or ID for the autocomplete dropdown.
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    q = request.GET.get('q', '').strip()
    if not q:
        agents = Agent.objects.all().order_by('-id')[:20]
    else:
        agents = Agent.objects.filter(
            Q(fullname__icontains=q) |
            Q(email__icontains=q) |
            Q(mobile__icontains=q) |
            Q(id__startswith=q)
        ).order_by('-id')[:25]

    results = []
    for ag in agents:
        profile = getattr(ag, 'profile', None)
        results.append({
            'id': ag.id,
            'fullname': ag.fullname,
            'email': ag.email,
            'mobile': ag.mobile,
            'status': ag.status,
            'agent_pincode': ag.agent_pincode or 'None',
            'has_coords': bool(ag.latitude and ag.longitude),
            'latitude': float(ag.latitude) if ag.latitude else None,
            'longitude': float(ag.longitude) if ag.longitude else None,
            'is_card_visible': bool(profile.is_card_visible) if profile else True,
        })

    return JsonResponse({'success': True, 'agents': results})


@require_http_methods(['POST'])
def assign_agent_to_pincode(request):
    """
    Assign pincode and coordinates to an existing Agent so they immediately appear
    in the Find Agent directory for this location.
    Options:
      - set_primary: update agent_pincode, latitude, longitude
      - add_service_pincode: add to agent's service pincodes list
      - activate: set status='active' and profile.is_card_visible=True
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    agent_id = data.get('agent_id')
    pincode = str(data.get('pincode', '')).strip()
    city_name = str(data.get('city_name', '')).strip() or 'Default'
    set_primary = bool(data.get('set_primary', True))
    add_service_pin = bool(data.get('add_service_pincode', True))
    activate_agent = bool(data.get('activate_agent', True))

    try:
        lat_val = data.get('latitude') if data.get('latitude') is not None else data.get('lat')
        lng_val = data.get('longitude') if data.get('longitude') is not None else data.get('lng')
        lat = float(lat_val)
        lng = float(lng_val)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Valid latitude and longitude are required.'}, status=422)

    if not agent_id or not pincode:
        return JsonResponse({'success': False, 'message': 'Agent ID and Pincode are required.'}, status=400)

    try:
        agent = Agent.objects.get(id=agent_id)
    except Agent.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Agent #{agent_id} not found.'}, status=404)

    find_agent_locator_service.assign_agent_to_pincode(
        agent, pincode, city_name, lat, lng, set_primary, add_service_pin, activate_agent,
    )

    logger.info(f"[FindAgentLocator] Agent #{agent.id} ({agent.fullname}) assigned to pincode {pincode} ({lat},{lng})")

    return JsonResponse({
        'success': True,
        'message': f"✅ Agent #{agent.id} ({agent.fullname}) successfully added to Find Agent list for pincode {pincode}!",
        'agent': {
            'id': agent.id,
            'fullname': agent.fullname,
            'email': agent.email,
            'status': agent.status,
            'agent_pincode': agent.agent_pincode,
            'latitude': float(agent.latitude) if agent.latitude else None,
            'longitude': float(agent.longitude) if agent.longitude else None,
        }
    })


@require_http_methods(['POST'])
def create_and_add_agent(request):
    """
    Quickly onboard/create a new agent and add them directly into the Find Agent list
    for the extracted pincode & coordinates.
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    fullname = str(data.get('fullname', '')).strip()
    mobile = str(data.get('mobile', '')).strip()
    email = str(data.get('email', '')).strip().lower()
    pincode = str(data.get('pincode', '')).strip()
    insurance_type = str(data.get('insurance_type', 'Life')).strip()
    company_name = str(data.get('company_name', 'LIC')).strip()
    city_name = str(data.get('city_name', '')).strip() or 'Default City'

    try:
        lat_val = data.get('latitude') if data.get('latitude') is not None else data.get('lat')
        lng_val = data.get('longitude') if data.get('longitude') is not None else data.get('lng')
        lat = float(lat_val)
        lng = float(lng_val)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'message': 'Valid latitude and longitude are required.'}, status=422)

    if not fullname or not mobile or not email or not pincode:
        return JsonResponse({'success': False, 'message': 'Fullname, Mobile, Email, and Pincode are required.'}, status=422)

    if Agent.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'message': f'An agent with email {email} already exists.'}, status=422)

    if Agent.objects.filter(mobile=mobile).exists():
        return JsonResponse({'success': False, 'message': f'An agent with mobile {mobile} already exists.'}, status=422)

    from apps.agents.services.account_auth import email_owned_by_non_agent_account

    if email_owned_by_non_agent_account(email):
        return JsonResponse({'success': False, 'message': f'This email ({email}) is associated with an admin or portal account and cannot be registered as an agent.'}, status=422)

    try:
        agent = find_agent_locator_service.create_agent(
            fullname, email, mobile, pincode, insurance_type, company_name, city_name, lat, lng,
        )

        logger.info(f"[FindAgentLocator] Quick created Agent #{agent.id} ({fullname}) in pincode {pincode}")

        return JsonResponse({
            'success': True,
            'message': f"🎉 Agent #{agent.id} ({fullname}) created and listed for pincode {pincode}!",
            'agent': {
                'id': agent.id,
                'fullname': agent.fullname,
                'email': agent.email,
                'mobile': agent.mobile,
                'pincode': pincode,
                'latitude': lat,
                'longitude': lng,
            }
        })
    except Exception as e:
        logger.error(f"[FindAgentLocator] Error creating agent: {e}")
        logger.exception("Admin request failed in find_agent_locator")  # detail stays server-side
        return JsonResponse({'success': False, 'message': "Error creating agent. Details are in the server log."}, status=500)


@require_http_methods(['GET', 'POST'])
def live_preview(request):
    """
    Simulate the exact public Find Agent directory logic for the given pincode & coordinates.
    Returns list of matching agents with match type (Direct 0 km / Proximity X km),
    distance, smart rank, active status, and profile link.
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    pincode = request.GET.get('pincode', '').strip()
    lat_val = request.GET.get('latitude')
    lng_val = request.GET.get('longitude')

    if not pincode and (not lat_val or not lng_val):
        return JsonResponse({'success': False, 'message': 'Pincode or Coordinates required.'}, status=400)

    user_lat = None
    user_lng = None
    if lat_val and lng_val:
        try:
            user_lat = float(lat_val)
            user_lng = float(lng_val)
        except (ValueError, TypeError):
            pass

    # If coordinates are missing, resolve them
    if (user_lat is None or user_lng is None) and pincode:
        geo_svc = GeocodingService()
        coords = geo_svc.resolve_coordinates(pincode)
        if coords:
            user_lat = coords.get('lat')
            user_lng = coords.get('lng')

    agents = _get_matching_agents_list(pincode, user_lat, user_lng)

    return JsonResponse({
        'success': True,
        'pincode': pincode,
        'user_lat': user_lat,
        'user_lng': user_lng,
        'total_found': len(agents),
        'agents': agents,
    })


@require_http_methods(['POST'])
def unlink_agent_pincode(request):
    """
    Remove this service pincode from an agent.
    """
    if not _check_admin(request):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    agent_id = data.get('agent_id')
    pincode = str(data.get('pincode', '')).strip()

    if not agent_id or not pincode:
        return JsonResponse({'success': False, 'message': 'Agent ID and Pincode are required.'}, status=400)

    try:
        agent = Agent.objects.get(id=agent_id)
        find_agent_locator_service.unlink_agent_pincode(agent, pincode)

        return JsonResponse({
            'success': True,
            'message': f"Pincode {pincode} removed from Agent #{agent.id}.",
        })
    except Exception as e:
        logger.exception("Admin request failed in find_agent_locator")  # detail stays server-side
        return JsonResponse({'success': False, 'message': "Error unlinking. Details are in the server log."}, status=500)


# ─── Helper Functions ────────────────────────────────────────────────────────

def _count_matching_agents(pincode, user_lat, user_lng, radius_km=NEARBY_RADIUS_KM):
    """Count how many active agents match this pincode or coordinates."""
    agents = _get_matching_agents_list(pincode, user_lat, user_lng, radius_km=radius_km)
    return len(agents)


def _get_matching_agents_list(pincode, user_lat, user_lng, radius_km=NEARBY_RADIUS_KM):
    """
    Return all active agents who:
      1. Directly serve this pincode (distance = 0 km)
      2. Or are within radius_km (50 km) of the coordinates
    """
    from django.db.models import Avg, FloatField, Q, Value
    from django.db.models.functions import Coalesce

    active_agents = (
        Agent.objects.filter(status='active')
        .exclude(profile__is_card_visible=False)
        .select_related('profile')
        .prefetch_related('servicePincodes')
        # Agent.average_rating reads _avg_rating; without it each agent cost 2 queries.
        .annotate(_avg_rating=Coalesce(Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
                                       Value(0.0), output_field=FloatField()))
    )

    results = []
    pincode_clean = pincode.strip() if pincode else ''
    coords_cache = {}  # many agents share service pincodes: one lookup each per call

    def pincode_coords(pin):
        if pin not in coords_cache:
            coords_cache[pin] = DistanceService.get_pincode_coordinates(pin)
        return coords_cache[pin]

    for agent in active_agents:
        profile = getattr(agent, 'profile', None)
        serves_direct = False
        if pincode_clean:
            serves_direct = agent_serves_pincode(agent, pincode_clean)

        distance = None
        if serves_direct:
            distance = 0.0
        elif user_lat is not None and user_lng is not None:
            if agent.latitude and agent.longitude:
                distance = DistanceService.calculate(user_lat, user_lng, agent.latitude, agent.longitude)
            if distance is None:
                # Check service pincodes coordinates
                for pin in iter_agent_service_pincodes(agent):
                    p_coords = pincode_coords(pin)
                    if p_coords:
                        d = DistanceService.calculate(user_lat, user_lng, p_coords['lat'], p_coords['lng'])
                        if d is not None and (distance is None or d < distance):
                            distance = d

        is_nearby = (distance is not None and distance <= radius_km)
        if serves_direct or is_nearby:
            results.append({
                'id': agent.id,
                'fullname': agent.fullname,
                'email': agent.email,
                'mobile': agent.mobile,
                'agent_pincode': agent.agent_pincode or '',
                'serves_direct': serves_direct,
                'distance': distance,
                'distance_str': 'Direct Pincode Match (0 km)' if serves_direct else f"{distance} km away",
                'latitude': float(agent.latitude) if agent.latitude else None,
                'longitude': float(agent.longitude) if agent.longitude else None,
                'plan_type': agent.plan_type or 'Standard',
                'badge': agent.badge or 'None',
                'average_rating': round(agent.average_rating, 1) if hasattr(agent, 'average_rating') else 0.0,
                'public_url': f"/find-agents/?pincode={pincode_clean}" if pincode_clean else "/find-agents/",
                'profile_slug': getattr(profile, 'slug', '') if profile else str(agent.id),
                'avatar_letter': (agent.fullname[0] if agent.fullname else 'A').upper(),
            })

    # Sort results: Direct matches first, then by distance ascending
    results.sort(key=lambda x: (
        0 if x['serves_direct'] else 1,
        x['distance'] if x['distance'] is not None else 999999,
        x['id']
    ))

    return results
