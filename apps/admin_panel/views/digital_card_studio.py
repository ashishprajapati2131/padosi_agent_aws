"""
apps/admin_panel/views/digital_card_studio.py

Admin Panel Controller for Personal Digital Visiting Card Studio Management:
1. Global Card Studio CMS & Section Visibility Policy Editor
2. Agent Digital Visiting Cards Directory with Live Search, Filter, and 1-Click Status Toggling
3. Quick Card Inspector & Override API (edit/reset any agent's card customizations)
4. Visiting Card Leads & Performance Analytics
"""

import json
import logging
from typing import Optional, Tuple
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.urls import reverse

from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel.models import AdminActivityLog
from apps.admin_panel.services.digital_card_studio import (
    get_digital_card_studio_config,
    save_digital_card_studio_config,
    DEFAULT_DIGITAL_CARD_STUDIO_CONFIG,
    VALID_POLICIES,
    VALID_BANNER_STYLES,
)
from apps.agents.models import Agent, AgentProfile, AgentLead, AgentProfileView
from apps.agents.views.qr import _ensure_profile

logger = logging.getLogger('apps.admin_panel.views.digital_card_studio')


def _check_admin_permission(request) -> Tuple[Optional[Admin], bool]:
    """
    Validate admin session and verify permission to manage visiting cards.
    Allowed: 'super' role, or 'content', 'agents', or 'site_settings' permissions.
    """
    admin_id = _get_admin_from_session(request)
    if not admin_id and hasattr(request, 'session'):
        admin_id = request.session.get('admin_id')
    if not admin_id:
        return None, False

    try:
        admin_obj = Admin.objects.filter(id=admin_id).first()
        if not admin_obj:
            return None, False

        if admin_obj.role == 'super':
            return admin_obj, True

        perms = admin_obj.permissions or []
        if isinstance(perms, str):
            try:
                perms = json.loads(perms)
            except Exception:
                perms = []

        if any(p in perms for p in ('content', 'agents', 'site_settings', 'feature_flags')):
            return admin_obj, True

        return admin_obj, False
    except Exception as e:
        logger.error(f"Error checking admin permissions: {e}")
        return None, False


def digital_card_studio_index(request):
    """
    Main dashboard for Personal Digital Visiting Card Studio in Admin Panel.
    Includes:
    - Global Section Visibility Policies & Visual CMS
    - Real-time searchable/filterable agent cards directory
    - Instant AJAX visibility toggle
    - Lead enquiries & performance overview
    """
    admin_obj, allowed = _check_admin_permission(request)
    if not admin_obj:
        return redirect('admin_login')
    if not allowed:
        messages.error(request, 'You do not have permission to access the Digital Visiting Card Studio.')
        return redirect('admin_dashboard')

    studio_cfg = get_digital_card_studio_config(use_cache=False)

    # 1. KPI Aggregates
    total_agents = Agent.objects.count()
    active_cards_count = AgentProfile.objects.filter(is_card_visible=True).exclude(
        agent__status__in=['suspended', 'deleted']
    ).count()
    hidden_cards_count = AgentProfile.objects.filter(is_card_visible=False).count()

    total_leads_count = AgentLead.objects.filter(
        Q(interaction_type='digital_card_enquiry') | Q(source_page='digital-card')
    ).count()

    total_views = AgentProfileView.objects.aggregate(total=Sum('view_count'))['total'] or 0

    # 2. Search & Filtering for Agents
    search_q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'all').strip()
    visibility_filter = request.GET.get('visibility', 'all').strip()
    page_num = request.GET.get('page', 1)

    agents_qs = Agent.objects.select_related('profile', 'user').all().order_by('-id')

    if search_q:
        agents_qs = agents_qs.filter(
            Q(fullname__icontains=search_q) |
            Q(email__icontains=search_q) |
            Q(mobile__icontains=search_q) |
            Q(profile__slug__icontains=search_q) |
            Q(profile__agency_name__icontains=search_q) |
            Q(city__icontains=search_q)
        )

    if status_filter != 'all':
        agents_qs = agents_qs.filter(status=status_filter)

    if visibility_filter == 'visible':
        agents_qs = agents_qs.filter(profile__is_card_visible=True)
    elif visibility_filter == 'hidden':
        agents_qs = agents_qs.filter(Q(profile__is_card_visible=False) | Q(profile__isnull=True))

    paginator = Paginator(agents_qs, 20)
    agents_page = paginator.get_page(page_num)

    # Decorate agents on this page with card details and live link
    agents_decorated = []
    for ag in agents_page:
        prof = getattr(ag, 'profile', None)
        card_slug = getattr(prof, 'slug', None) or ag.agent_slug
        is_visible = getattr(prof, 'is_card_visible', True) if prof else True
        cfg = prof.get_card_config() if prof else {}

        # Lead count for this specific agent from card
        card_leads = AgentLead.objects.filter(
            agent=ag,
            interaction_type='digital_card_enquiry'
        ).count()

        agents_decorated.append({
            'agent': ag,
            'profile': prof,
            'card_slug': card_slug,
            'card_url': reverse('agents:agent_public_card', kwargs={'slug': card_slug}),
            'is_card_visible': is_visible,
            'theme_color': cfg.get('theme_color') or studio_cfg.get('default_theme_color', '#0B1F3A'),
            'banner_style': cfg.get('banner_style') or studio_cfg.get('default_banner_style', 'profile'),
            'agency_name': (cfg.get('agency_name') or getattr(prof, 'agency_name', '') or ag.fullname or '').strip(),
            'card_leads': card_leads,
        })

    # 3. Recent 15 Card Leads
    recent_leads = AgentLead.objects.filter(
        Q(interaction_type='digital_card_enquiry') | Q(source_page='digital-card')
    ).select_related('agent').order_by('-created_at')[:15]

    context = {
        'admin_obj': admin_obj,
        'config': studio_cfg,
        'kpi': {
            'total_agents': total_agents,
            'active_cards': active_cards_count,
            'hidden_cards': hidden_cards_count,
            'total_leads': total_leads_count,
            'total_views': total_views,
        },
        'agents_page': agents_page,
        'agents_decorated': agents_decorated,
        'recent_leads': recent_leads,
        'search_q': search_q,
        'status_filter': status_filter,
        'visibility_filter': visibility_filter,
        'valid_policies': VALID_POLICIES,
        'banner_styles': list(VALID_BANNER_STYLES),
    }

    return render(request, 'admin/content/visiting_card_studio.html', context)


@require_POST
def update_studio_config(request):
    """Save global studio configuration, content headers, permissions, and section policies."""
    admin_obj, allowed = _check_admin_permission(request)
    if not admin_obj or not allowed:
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    updates = {
        'enabled': request.POST.get('enabled') == '1',
        'studio_title': request.POST.get('studio_title', '').strip(),
        'studio_subtitle': request.POST.get('studio_subtitle', '').strip(),
        'studio_badge': request.POST.get('studio_badge', '').strip(),
        'style_badge': request.POST.get('style_badge', '').strip(),

        # Permissions
        'allow_theme_customization': request.POST.get('allow_theme_customization') == '1',
        'allow_custom_banner': request.POST.get('allow_custom_banner') == '1',
        'allow_custom_logo': request.POST.get('allow_custom_logo') == '1',
        'allow_custom_button': request.POST.get('allow_custom_button') == '1',
        'allow_lead_form_toggle': request.POST.get('allow_lead_form_toggle') == '1',

        # Branding Watermark
        'show_powered_by_badge': request.POST.get('show_powered_by_badge') == '1',
        'powered_by_text': request.POST.get('powered_by_text', '').strip() or 'Powered by PadosiAgent',
        'powered_by_url': request.POST.get('powered_by_url', '').strip() or '/',

        # Defaults
        'default_theme_color': request.POST.get('default_theme_color', '#0B1F3A').strip(),
        'default_banner_style': request.POST.get('default_banner_style', 'profile').strip(),
        'default_whatsapp_msg': request.POST.get('default_whatsapp_msg', '').strip(),
        'default_card_tagline': request.POST.get('default_card_tagline', '').strip(),
        'default_card_bio': request.POST.get('default_card_bio', '').strip(),

        # Section Policies
        'policy_call': request.POST.get('policy_call', 'allow_agent'),
        'policy_whatsapp': request.POST.get('policy_whatsapp', 'allow_agent'),
        'policy_email': request.POST.get('policy_email', 'allow_agent'),
        'policy_address': request.POST.get('policy_address', 'allow_agent'),
        'policy_save_contact': request.POST.get('policy_save_contact', 'allow_agent'),
        'policy_lead_form': request.POST.get('policy_lead_form', 'allow_agent'),
        'policy_services': request.POST.get('policy_services', 'allow_agent'),
        'policy_reviews': request.POST.get('policy_reviews', 'allow_agent'),
        'policy_qr_card': request.POST.get('policy_qr_card', 'allow_agent'),

        # SEO
        'meta_title_pattern': request.POST.get('meta_title_pattern', '').strip(),
        'meta_description_pattern': request.POST.get('meta_description_pattern', '').strip(),
    }

    saved = save_digital_card_studio_config(updates, request=request)
    messages.success(request, 'Digital Visiting Card Studio settings & policies updated successfully.')
    return redirect('admin_digital_card_studio')


@require_POST
def toggle_agent_card_visibility(request, agent_id):
    """
    AJAX endpoint to toggle an agent's digital visiting card visibility directly from Admin.
    """
    admin_obj, allowed = _check_admin_permission(request)
    if not admin_obj or not allowed:
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    agent = get_object_or_404(Agent, id=agent_id)
    _ensure_profile(agent, agent.agent_slug)
    profile = agent.get_primary_profile() or getattr(agent, 'profile', None)

    # Toggle
    current_status = getattr(profile, 'is_card_visible', True)
    new_status = not current_status
    profile.is_card_visible = new_status
    profile.save(update_fields=['is_card_visible', 'updated_at'])

    status_str = "Visible / Live" if new_status else "Hidden"
    AdminActivityLog.log(
        f"Admin toggled digital visiting card for '{agent.fullname}' to {status_str}",
        'AgentProfile',
        request=request
    )

    return JsonResponse({
        'success': True,
        'agent_id': agent.id,
        'agent_name': agent.fullname,
        'is_card_visible': new_status,
        'message': f"Card for {agent.fullname} is now {status_str}.",
    })


@require_http_methods(["GET"])
def admin_agent_card_detail_api(request, agent_id):
    """
    API endpoint returning an individual agent's card settings for the admin inspection modal.
    """
    admin_obj, allowed = _check_admin_permission(request)
    if not admin_obj or not allowed:
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    agent = get_object_or_404(Agent, id=agent_id)
    _ensure_profile(agent, agent.agent_slug)
    profile = agent.get_primary_profile() or getattr(agent, 'profile', None)
    cfg = profile.get_card_config() if profile else {}

    return JsonResponse({
        'success': True,
        'agent': {
            'id': agent.id,
            'fullname': agent.fullname,
            'email': agent.email,
            'mobile': agent.mobile,
            'status': agent.status,
            'slug': profile.slug if profile else agent.agent_slug,
            'card_url': reverse('agents:agent_public_card', kwargs={'slug': profile.slug if profile else agent.agent_slug}),
            'is_card_visible': getattr(profile, 'is_card_visible', True),
            'agency_name': (profile.agency_name if profile else '') or cfg.get('agency_name', ''),
            'card_tagline': (profile.card_tagline if profile else '') or cfg.get('tagline', ''),
            'card_bio': cfg.get('bio', '') or (profile.career_highlights if profile else '') or '',
            'theme_color': cfg.get('theme_color', '#0B1F3A'),
            'banner_style': cfg.get('banner_style', 'profile'),
            'whatsapp_msg': cfg.get('whatsapp_msg', ''),
            'custom_button_label': cfg.get('custom_button_label', ''),
            'custom_button_url': cfg.get('custom_button_url', ''),
            'show_call': cfg.get('show_call', True),
            'show_whatsapp': cfg.get('show_whatsapp', True),
            'show_lead_form': cfg.get('show_lead_form', True),
            'show_reviews': cfg.get('show_reviews', True),
        }
    })


@require_POST
def admin_agent_card_save_api(request, agent_id):
    """
    API endpoint for admin to override/update an individual agent's card settings
    or reset them to system defaults.
    """
    admin_obj, allowed = _check_admin_permission(request)
    if not admin_obj or not allowed:
        return JsonResponse({'success': False, 'message': 'Permission denied.'}, status=403)

    agent = get_object_or_404(Agent, id=agent_id)
    _ensure_profile(agent, agent.agent_slug)
    profile = agent.get_primary_profile() or getattr(agent, 'profile', None)

    action = request.POST.get('action', 'save')

    if action == 'reset':
        # Reset card customizations to defaults
        profile.card_config = {}
        profile.is_card_visible = True
        profile.save(update_fields=['card_config', 'is_card_visible', 'updated_at'])
        AdminActivityLog.log(
            f"Admin reset visiting card customizations for '{agent.fullname}' to default",
            'AgentProfile',
            request=request
        )
        return JsonResponse({
            'success': True,
            'message': f"Card for {agent.fullname} has been reset to system defaults.",
            'is_card_visible': True,
        })

    # Save overrides
    cfg = profile.get_card_config()

    agency_name = request.POST.get('agency_name', '').strip()
    card_tagline = request.POST.get('card_tagline', '').strip()
    card_bio = request.POST.get('card_bio', '').strip()
    theme_color = request.POST.get('theme_color', '').strip()
    banner_style = request.POST.get('banner_style', '').strip()
    custom_button_label = request.POST.get('custom_button_label', '').strip()
    custom_button_url = request.POST.get('custom_button_url', '').strip()
    whatsapp_msg = request.POST.get('whatsapp_msg', '').strip()
    slug_val = request.POST.get('slug', '').strip()

    if agency_name:
        profile.agency_name = agency_name
        cfg['agency_name'] = agency_name
    if card_tagline:
        profile.card_tagline = card_tagline
        cfg['tagline'] = card_tagline
    if card_bio:
        cfg['bio'] = card_bio
    if theme_color:
        cfg['theme_color'] = theme_color
    if banner_style in VALID_BANNER_STYLES:
        cfg['banner_style'] = banner_style
    if custom_button_label:
        cfg['custom_button_label'] = custom_button_label
    if custom_button_url:
        cfg['custom_button_url'] = custom_button_url
    if whatsapp_msg:
        cfg['whatsapp_msg'] = whatsapp_msg

    if 'is_card_visible' in request.POST:
        profile.is_card_visible = request.POST.get('is_card_visible') == '1'

    # If slug changed, ensure uniqueness
    if slug_val and slug_val != profile.slug:
        from django.utils.text import slugify
        new_slug = slugify(slug_val) or slug_val
        if not AgentProfile.objects.filter(slug=new_slug).exclude(id=profile.id).exists():
            profile.slug = new_slug

    profile.card_config = cfg
    profile.save(update_fields=['agency_name', 'card_tagline', 'slug', 'is_card_visible', 'card_config', 'updated_at'])

    AdminActivityLog.log(
        f"Admin updated visiting card overrides for '{agent.fullname}'",
        'AgentProfile',
        request=request
    )

    return JsonResponse({
        'success': True,
        'message': f"Visiting card settings for {agent.fullname} updated successfully.",
        'slug': profile.slug,
        'is_card_visible': profile.is_card_visible,
        'card_url': reverse('agents:agent_public_card', kwargs={'slug': profile.slug}),
    })
