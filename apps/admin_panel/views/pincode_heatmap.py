import json
import logging
import re
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib import messages
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.home.models.site_setting import SiteSetting
from apps.agents.models import Agent, City
from apps.home.models import Pincode, PincodeCache
from apps.home.services.distance import DistanceService
from django.db.models import Count, Q

logger = logging.getLogger(__name__)

# Baseline clusters for prominent hubs so the map is populated even before user activity
DEFAULT_CORE_CLUSTERS = [
    {"pincode": "380001", "name": "Ahmedabad Central (GPO)", "district": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lng": 72.5714, "count": 18, "type": "high", "demand_count": 4},
    {"pincode": "380015", "name": "Satellite / Bodakdev", "district": "Ahmedabad", "state": "Gujarat", "lat": 23.0200, "lng": 72.5100, "count": 12, "type": "high", "demand_count": 3},
    {"pincode": "395007", "name": "Surat (Vesu / Ring Road)", "district": "Surat", "state": "Gujarat", "lat": 21.1702, "lng": 72.8311, "count": 12, "type": "high", "demand_count": 2},
    {"pincode": "390001", "name": "Vadodara Central", "district": "Vadodara", "state": "Gujarat", "lat": 22.3072, "lng": 73.1812, "count": 8, "type": "medium", "demand_count": 1},
    {"pincode": "360001", "name": "Rajkot Central", "district": "Rajkot", "state": "Gujarat", "lat": 22.3039, "lng": 70.8022, "count": 6, "type": "medium", "demand_count": 1},
    {"pincode": "382010", "name": "Gandhinagar Infocity", "district": "Gandhinagar", "state": "Gujarat", "lat": 23.2156, "lng": 72.6369, "count": 5, "type": "medium", "demand_count": 0},
    {"pincode": "400001", "name": "Mumbai Fort / GPO", "district": "Mumbai", "state": "Maharashtra", "lat": 18.9220, "lng": 72.8347, "count": 15, "type": "high", "demand_count": 5},
    {"pincode": "411001", "name": "Pune Camp", "district": "Pune", "state": "Maharashtra", "lat": 18.5204, "lng": 73.8567, "count": 9, "type": "medium", "demand_count": 2},
    {"pincode": "110001", "name": "Delhi Connaught Place", "district": "New Delhi", "state": "Delhi", "lat": 28.6353, "lng": 77.2250, "count": 14, "type": "high", "demand_count": 4},
    {"pincode": "364001", "name": "Bhavnagar (Opportunity)", "district": "Bhavnagar", "state": "Gujarat", "lat": 21.7645, "lng": 72.1519, "count": 0, "type": "opportunity", "demand_count": 2},
    {"pincode": "361001", "name": "Jamnagar (Opportunity)", "district": "Jamnagar", "state": "Gujarat", "lat": 22.4707, "lng": 70.0577, "count": 0, "type": "opportunity", "demand_count": 2},
]


def _build_pincode_heatmap_data():
    """
    Extract and aggregate dynamic geospatial pincode clusters from:
    1. Active registered agents with agent_pincode
    2. AgentServicePincode records
    3. ContactSubmission lead inquiries
    4. Baseline curated hubs
    """
    clusters = {}

    # Seed baseline hubs
    for c in DEFAULT_CORE_CLUSTERS:
        clusters[c['pincode']] = dict(c)

    # 1. Real Agents with primary pincodes
    try:
        agent_counts = (
            Agent.objects.filter(status='active')
            .exclude(agent_pincode='')
            .values('agent_pincode')
            .annotate(cnt=Count('id'))
        )
        for row in agent_counts:
            pin = str(row['agent_pincode']).strip()
            if not re.match(r'^[1-9]\d{5}$', pin):
                continue
            cnt = row['cnt']
            if pin in clusters:
                clusters[pin]['count'] = max(clusters[pin]['count'], cnt)
            else:
                clusters[pin] = {
                    'pincode': pin,
                    'name': f"PIN {pin}",
                    'district': '',
                    'state': '',
                    'lat': None,
                    'lng': None,
                    'count': cnt,
                    'demand_count': 0,
                    'type': 'high' if cnt >= 5 else 'medium',
                }
    except Exception as e:
        logger.warning(f"[Heatmap] Failed fetching Agent primary pincodes: {e}")

    # 2. AgentServicePincode
    try:
        from apps.admin_panel.models import AgentServicePincode
        svc_counts = (
            AgentServicePincode.objects.filter(agent__status='active')
            .values('service_pincode', 'city_name')
            .annotate(cnt=Count('agent', distinct=True))
        )
        for row in svc_counts:
            pin = str(row['service_pincode']).strip()
            if not re.match(r'^[1-9]\d{5}$', pin):
                continue
            cnt = row['cnt']
            city = row.get('city_name') or ''
            if pin in clusters:
                clusters[pin]['count'] = max(clusters[pin]['count'], cnt)
                if city and 'PIN' in clusters[pin]['name']:
                    clusters[pin]['name'] = f"{city} ({pin})"
            else:
                clusters[pin] = {
                    'pincode': pin,
                    'name': f"{city} ({pin})" if city else f"PIN {pin}",
                    'district': city,
                    'state': '',
                    'lat': None,
                    'lng': None,
                    'count': cnt,
                    'demand_count': 0,
                    'type': 'high' if cnt >= 5 else 'medium',
                }
    except Exception as e:
        logger.warning(f"[Heatmap] Failed fetching AgentServicePincode: {e}")

    # 3. Customer Demand (ContactSubmission leads)
    try:
        from apps.admin_panel.models.contact_submission import ContactSubmission
        leads = ContactSubmission.objects.all().values('message')[:150]
        for item in leads:
            msg = item.get('message') or ''
            pins = re.findall(r'\b[1-9]\d{5}\b', msg)
            for pin in pins:
                if pin in clusters:
                    clusters[pin]['demand_count'] = clusters[pin].get('demand_count', 0) + 1
                else:
                    clusters[pin] = {
                        'pincode': pin,
                        'name': f"Customer Demand ({pin})",
                        'district': '',
                        'state': '',
                        'lat': None,
                        'lng': None,
                        'count': 0,
                        'demand_count': 1,
                        'type': 'opportunity',
                    }
    except Exception as e:
        logger.warning(f"[Heatmap] Failed fetching demand leads: {e}")

    # Resolve coordinates and locality names for any cluster missing lat/lng
    for pin, item in list(clusters.items()):
        # Calculate supply / demand classification
        if item['count'] >= 5:
            item['type'] = 'high'
        elif item['count'] > 0:
            item['type'] = 'medium'
        else:
            item['type'] = 'opportunity'

        if item['lat'] and item['lng']:
            continue

        # Check precise curated
        exact = DistanceService.get_precise_pincode_coordinates(pin)
        if exact:
            item['lat'] = float(exact['lat'])
            item['lng'] = float(exact['lng'])
            if not item.get('district'): item['district'] = exact.get('district', '')
            if not item.get('state'): item['state'] = exact.get('state', '')
            item['name'] = f"{exact.get('office_name') or exact.get('district') or pin} ({pin})"
            continue

        # Check Pincode master table
        try:
            db_pin = Pincode.objects.filter(pincode=pin).first()
            if db_pin and db_pin.latitude and db_pin.longitude:
                item['lat'] = float(db_pin.latitude)
                item['lng'] = float(db_pin.longitude)
                item['district'] = db_pin.district or ''
                item['state'] = db_pin.state or ''
                item['name'] = f"{db_pin.formatted_location or db_pin.office_name} ({pin})"
                continue
        except Exception:
            pass

        # Check PincodeCache
        try:
            cache_pin = PincodeCache.objects.filter(pincode=pin).first()
            if cache_pin and cache_pin.latitude and cache_pin.longitude:
                item['lat'] = float(cache_pin.latitude)
                item['lng'] = float(cache_pin.longitude)
                item['name'] = f"{cache_pin.display_name or pin} ({pin})"
                continue
        except Exception:
            pass

        # Regional fallback
        fallback = DistanceService.get_regional_fallback_coordinates(pin)
        if fallback:
            item['lat'] = float(fallback['lat'])
            item['lng'] = float(fallback['lng'])

    valid_clusters = [c for c in clusters.values() if c.get('lat') is not None and c.get('lng') is not None]
    return valid_clusters


def pincode_heatmap_index(request):
    """Business Intelligence (BI) Heatmap: Demand vs. Supply mapping with Feature Flag controls."""
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')

    feature_flag_active = SiteSetting.get_value('feature_flag_pincode_heatmap', True)

    # Calculate real supply and demand metrics
    try:
        total_pincodes = Pincode.objects.count()
    except Exception:
        total_pincodes = 0

    try:
        total_active_agents = Agent.objects.filter(status='active').count()
    except Exception:
        total_active_agents = 0

    try:
        cities_with_agents = City.objects.filter(agents__status='active').distinct().count()
    except Exception:
        cities_with_agents = 0

    # Top cities by agent supply
    top_supply_cities = []
    try:
        top_supply_cities = (
            City.objects.filter(agents__status='active')
            .annotate(agent_count=Count('agents', filter=Q(agents__status='active')))
            .order_by('-agent_count')[:6]
        )
    except Exception:
        top_supply_cities = []

    # High Opportunity Cities (Cities where we have active city entries but 0 agents)
    opportunity_cities = []
    try:
        opportunity_cities = (
            City.objects.filter(is_active=True)
            .annotate(agent_count=Count('agents', filter=Q(agents__status='active')))
            .filter(agent_count=0)[:6]
        )
    except Exception:
        opportunity_cities = []

    # Dynamic clusters
    clusters_data = _build_pincode_heatmap_data()
    high_supply_count = sum(1 for c in clusters_data if c['type'] == 'high')
    medium_supply_count = sum(1 for c in clusters_data if c['type'] == 'medium')
    opportunity_count = sum(1 for c in clusters_data if c['type'] == 'opportunity')

    context = {
        'feature_flag_active': feature_flag_active,
        'total_pincodes': total_pincodes,
        'total_active_agents': total_active_agents,
        'cities_with_agents': cities_with_agents,
        'top_supply_cities': top_supply_cities,
        'opportunity_cities': opportunity_cities,
        'clusters_json': json.dumps(clusters_data),
        'total_clusters': len(clusters_data),
        'high_supply_count': high_supply_count,
        'medium_supply_count': medium_supply_count,
        'opportunity_count': opportunity_count,
    }
    return render(request, 'admin/pincode/heatmap.html', context)


def pincode_lookup(request):
    """
    Real-time AJAX lookup for any 6-digit Indian PIN code to locate and plot on the BI heatmap.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    pin = str(request.GET.get('pincode', '')).strip()
    if not pin or not re.match(r'^[1-9]\d{5}$', pin):
        return JsonResponse({
            'success': False,
            'message': 'Please provide a valid 6-digit Indian PIN code (e.g. 380015).'
        }, status=400)

    # Agents count
    agent_count = 0
    try:
        agent_count = Agent.objects.filter(status='active', agent_pincode=pin).count()
        from apps.admin_panel.models import AgentServicePincode
        svc_count = AgentServicePincode.objects.filter(
            agent__status='active', service_pincode=pin
        ).values('agent_id').distinct().count()
        agent_count = max(agent_count, svc_count)
    except Exception:
        pass

    # Demand count
    demand_count = 0
    try:
        from apps.admin_panel.models.contact_submission import ContactSubmission
        demand_count = ContactSubmission.objects.filter(message__icontains=pin).count()
    except Exception:
        pass

    # Resolve coordinates and locality
    lat = None
    lng = None
    office_name = f"PIN {pin}"
    district = ""
    state = ""

    exact = DistanceService.get_precise_pincode_coordinates(pin)
    if exact:
        lat = float(exact['lat'])
        lng = float(exact['lng'])
        office_name = exact.get('office_name') or f"PIN {pin}"
        district = exact.get('district', '')
        state = exact.get('state', '')
    else:
        try:
            db_pin = Pincode.objects.filter(pincode=pin).first()
            if db_pin and db_pin.latitude and db_pin.longitude:
                lat = float(db_pin.latitude)
                lng = float(db_pin.longitude)
                office_name = db_pin.office_name or f"PIN {pin}"
                district = db_pin.district or ''
                state = db_pin.state or ''
        except Exception:
            pass

    if lat is None or lng is None:
        try:
            from apps.home.services.geocoding import GeocodingService
            geo = GeocodingService().resolve_coordinates(pin)
            if geo and geo.get('lat') and geo.get('lng'):
                lat = float(geo['lat'])
                lng = float(geo['lng'])
                disp = geo.get('display_name', '')
                parts = [p.strip() for p in disp.split(',') if p.strip()]
                office_name = parts[0] if parts else f"PIN {pin}"
                if len(parts) > 1: district = parts[1]
                if len(parts) > 2: state = parts[2]
        except Exception:
            pass

    if lat is None or lng is None:
        fallback = DistanceService.get_regional_fallback_coordinates(pin)
        if fallback:
            lat = float(fallback['lat'])
            lng = float(fallback['lng'])

    if lat is None or lng is None:
        return JsonResponse({
            'success': False,
            'message': f"Coordinates could not be found for pincode {pin}."
        }, status=404)

    status_type = 'high' if agent_count >= 5 else ('medium' if agent_count > 0 else 'opportunity')

    return JsonResponse({
        'success': True,
        'data': {
            'pincode': pin,
            'name': f"{office_name} ({pin})",
            'office_name': office_name,
            'district': district,
            'state': state,
            'lat': lat,
            'lng': lng,
            'count': agent_count,
            'demand_count': demand_count,
            'type': status_type,
        }
    })


def toggle_heatmap_flag(request):
    """Toggle the Feature Flag for Pincode Heatmap BI module."""
    admin_id = _get_admin_from_session(request)
    if not admin_id: return redirect('admin_login')

    current_flag = SiteSetting.get_value('feature_flag_pincode_heatmap', True)
    new_flag = not current_flag
    SiteSetting.set_value('feature_flag_pincode_heatmap', new_flag, 'system')

    status = "Enabled (Active Staging)" if new_flag else "Disabled (Hidden)"
    AdminActivityLog.log(f'Toggled Pincode Heatmap Feature Flag: {status}', 'SiteSetting', request=request)
    messages.success(request, f'Pincode Heatmap BI Feature Flag is now {status}.')

    return redirect('admin_pincode_heatmap')
