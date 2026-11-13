"""Pincode lookup endpoints and the shared _get_or_create_pincode helper."""
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_GET
import re
import logging
import requests as http_requests
from apps.agents.models import Agent
from apps.home.models import Pincode
from django.db.models import Q
from django.core.cache import cache

# Keep the original logger name so log lines/filters are unchanged.
logger = logging.getLogger('apps.home.views.pages')


@require_GET
def pincode_fetch(request, pincode):
    if not re.match(r'^[1-9]\d{5}$', pincode):
        return JsonResponse({'success': False, 'message': 'Invalid pincode format.'})

    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    ip = ThreatMonitorMiddleware.get_client_ip(request)
    # Each uncached pincode can run 2 external lookups; cap one IP at 30/minute (audit WEB3).
    rl_key = f'rl_pincode_fetch_{ip}'
    if not cache.add(rl_key, 1, timeout=60):
        if cache.incr(rl_key) > 30:
            return JsonResponse(
                {'success': False, 'message': 'Too many requests. Try again shortly.'}, status=429
            )

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
        cache.set(cache_key, {'success': False, 'message': 'Pincode not found.'}, timeout=86400)
        return JsonResponse({'success': False, 'message': 'Pincode not found.'})

    formatted_location = record.formatted_location
    
    # Try to enhance the location name using GeocodingService (mirrors PHP behavior)
    from apps.home.services.geocoding import GeocodingService
    geo_svc = GeocodingService()
    resolved = geo_svc.resolve_coordinates(pincode)
    
    if resolved and resolved.get('display_name'):
        formatted_location = resolved['display_name']  # shown here only; never saved (audit WEB5).

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
