from django.shortcuts import render, redirect
from django.contrib import messages
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_activity_log import AdminActivityLog
from apps.home.models.site_setting import SiteSetting
from apps.agents.models import Agent, City
from apps.home.models import Pincode
from django.db.models import Count, Q


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

    context = {
        'feature_flag_active': feature_flag_active,
        'total_pincodes': total_pincodes,
        'total_active_agents': total_active_agents,
        'cities_with_agents': cities_with_agents,
        'top_supply_cities': top_supply_cities,
        'opportunity_cities': opportunity_cities,
    }
    return render(request, 'admin/pincode/heatmap.html', context)


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
