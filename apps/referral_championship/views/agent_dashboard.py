import json
import logging
import re
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.agents.models import Agent
from apps.agents.services.feature_unlock import profile_completion_percent
from apps.agents.services.review_growth import agent_review_count
from apps.referral_championship.models import (
    ChampionshipCampaign,
    ChampionshipParticipant,
    ChampionshipReferral,
    ChampionshipRewardSlab,
    ChampionshipRewardClaim,
)
from apps.referral_championship.services.attribution_service import get_or_create_participant
from apps.referral_championship.services.reward_engine import (
    CLAIM_CONTACT_MESSAGE,
    CLAIM_EDITABLE_STATUSES,
    VOUCHER_REWARD_TYPES,
    slab_is_claimable,
    format_inr,
    get_participant_roadmap,
)
from apps.referral_championship.services.leaderboard_service import (
    get_leaderboard_data,
    get_campaign_aggregate_stats,
    refresh_leaderboard_cache,
)
from apps.referral_championship.services.whatsapp_service import (
    WHATSAPP_TEMPLATES,
    render_whatsapp_message,
    get_whatsapp_share_url,
)
from apps.referral_championship.services.share_service import (
    generate_qr_base64,
    generate_qr_bytes,
)

logger = logging.getLogger(__name__)


def _resolve_championship_unlock_gate(agent, campaign, participant, completion, review_count):
    """Profile/review thresholds; event-registration challengers are always unlocked."""
    from apps.event_referral.services.participant_service import (
        event_referral_bypasses_championship_unlock,
    )

    unlock_cfg = campaign.unlock_config if isinstance(campaign.unlock_config, dict) else {}
    min_profile = int(unlock_cfg.get('min_profile_percent') or 80)
    min_reviews = int(unlock_cfg.get('min_reviews') or 10)

    if event_referral_bypasses_championship_unlock(agent):
        is_unlocked = True
    else:
        is_unlocked = completion >= min_profile and review_count >= min_reviews

    if is_unlocked and not participant.is_unlocked:
        participant.is_unlocked = True
        participant.profile_completed_at = timezone.now()
        participant.reviews_completed_at = timezone.now()
        participant.save(update_fields=['is_unlocked', 'profile_completed_at', 'reviews_completed_at'])

    return is_unlocked, min_profile, min_reviews


def build_safe_absolute_uri(request, path_or_url):
    """
    Build an absolute URI from the request, ensuring that in production (DEBUG=False)
    no localhost/127.0.0.1 origins leak into client/mobile API payloads behind reverse proxies.
    """
    if not path_or_url:
        return path_or_url
    try:
        uri = request.build_absolute_uri(path_or_url)
    except Exception:
        clean_path = path_or_url if path_or_url.startswith('/') else f'/{path_or_url}'
        return f"https://www.padosiagent.com{clean_path}"

    if not getattr(settings, 'DEBUG', False) and any(h in uri.lower() for h in ('localhost', '127.0.0.1')):
        uri = re.sub(r'^https?://(localhost|127\.0\.0\.1)(:\d+)?', 'https://www.padosiagent.com', uri)
    return uri


def _referral_funnel_for_dashboard(request, agent, participant):
    """Championship PA- funnel, or EV- Paldi funnel when the agent is an event challenger."""
    from apps.event_referral.services.championship_dashboard import (
        build_event_referral_championship_context,
    )

    evt_ctx = build_event_referral_championship_context(
        request,
        agent,
        lambda path: build_safe_absolute_uri(request, path),
    )
    if evt_ctx:
        # Paldi referrals also count in the championship (owner decision
        # 2026-10-02), so show the same total the road and slabs use.
        evt_ctx['qualified_count'] = max(evt_ctx['qualified_count'] or 0,
                                         participant.qualifying_referrals_count or 0)
        return evt_ctx

    referrals_qs = ChampionshipReferral.objects.filter(referrer=participant)
    invited_count = referrals_qs.count()
    form_filled_count = referrals_qs.exclude(registration_state='started').count()
    paid_count = referrals_qs.filter(registration_state__in=['paid', 'active']).count()
    qualified_count = participant.qualifying_referrals_count

    domain = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    if not getattr(settings, 'DEBUG', False) and any(h in domain.lower() for h in ('localhost', '127.0.0.1')):
        domain = 'padosiagent.com'
        scheme = 'https'
    referral_url = f"{scheme}://{domain}/agent-registration/join/{participant.referral_id}/"

    recent_referrals = list(referrals_qs.order_by('-created_at')[:20])
    recent_referrals_api = []
    for ref in recent_referrals:
        agent_name = ref.referred_agent.fullname if ref.referred_agent and ref.referred_agent.fullname else 'Agent Registration'
        initials = (agent_name[:2] if agent_name else 'AG').upper()
        recent_referrals_api.append({
            'id': ref.id,
            'event_referral': False,
            'referred_agent_name': agent_name,
            'initials': initials,
            'created_at': ref.created_at.isoformat() if ref.created_at else None,
            'created_at_formatted': ref.created_at.strftime("%d %b, %I:%M %p") if ref.created_at else "",
            'registration_state': ref.registration_state,
        })

    return {
        'event_referral_mode': False,
        'event_referral_participant': None,
        'event_referral_all': [],
        'display_referral_id': participant.referral_id,
        'referral_url': referral_url,
        'invited_count': invited_count,
        'form_filled_count': form_filled_count,
        'paid_count': paid_count,
        'qualified_count': qualified_count,
        'referrals_target': None,
        'recent_referrals': recent_referrals,
        'recent_referrals_api': recent_referrals_api,
    }


def build_championship_dashboard_json_payload(request, agent):
    """
    Construct complete, structured JSON payload for Agent Championship Dashboard API.
    Covers all 9 dashboard sections with absolute image URLs.
    """
    campaign = ChampionshipCampaign.get_current()
    participant = get_or_create_participant(agent, campaign)

    # ── Unlock Gate Requirements ──
    completion = profile_completion_percent(agent)
    review_count = agent_review_count(agent)

    is_unlocked, min_profile, min_reviews = _resolve_championship_unlock_gate(
        agent, campaign, participant, completion, review_count,
    )
    profile_satisfied = is_unlocked or completion >= min_profile
    reviews_satisfied = is_unlocked or review_count >= min_reviews

    funnel = _referral_funnel_for_dashboard(request, agent, participant)
    invited_count = funnel['invited_count']
    form_filled_count = funnel['form_filled_count']
    paid_count = funnel['paid_count']
    qualified_count = funnel['qualified_count']
    referral_url = funnel['referral_url']
    recent_referrals_api = funnel['recent_referrals_api']

    # ── Roadmap & Next Reward ──
    roadmap_data = get_participant_roadmap(participant)

    qr_base64 = generate_qr_base64(referral_url)
    qr_download_url = build_safe_absolute_uri(request, reverse('championship:agent_qr_download'))

    # ── Leaderboard Data ──
    top_10 = get_leaderboard_data(campaign, limit=10)
    top_50 = get_leaderboard_data(campaign, limit=50)
    agg_stats = get_campaign_aggregate_stats(campaign)

    # WhatsApp default message
    pricing = campaign.pricing_config if isinstance(campaign.pricing_config, dict) else {}
    dig_price_raw = (pricing.get('digital') or {}).get('campaign_price', 999) if isinstance(pricing.get('digital'), dict) else 999
    prof_price_raw = (pricing.get('professional') or {}).get('campaign_price', 4999) if isinstance(pricing.get('professional'), dict) else 4999
    try:
        dig_price = int(dig_price_raw or 999)
    except (TypeError, ValueError):
        dig_price = 999
    try:
        prof_price = int(prof_price_raw or 4999)
    except (TypeError, ValueError):
        prof_price = 4999

    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else getattr(agent, 'profile', None)
    agent_slug_val = (getattr(profile, 'slug', None) if profile else None) or getattr(agent, 'agent_slug', None) or str(getattr(agent, 'id', ''))
    state_code = getattr(agent, 'state_code', 'gj')
    if callable(state_code):
        state_code = state_code()
    state_code = str(state_code or 'gj').strip().lower()
    profile_url = build_safe_absolute_uri(request, f"/{state_code}/{agent_slug_val}/")
    review_url = f"https://www.padosiagent.com/review/{agent_slug_val}/"

    default_wa_text = render_whatsapp_message(
        WHATSAPP_TEMPLATES['en']['templates'][0]['text'],
        agent_name=agent.fullname,
        referral_link=referral_url,
        profile_link=profile_url,
        digital_price=dig_price,
        professional_price=prof_price
    )
    default_wa_url = get_whatsapp_share_url(default_wa_text)

    # Multi-lingual WhatsApp studio text dictionary
    whatsapp_languages = {}
    for lang_code, lang_data in WHATSAPP_TEMPLATES.items():
        tmpl_text = lang_data.get('templates', [{}])[0].get('text', '')
        rendered_msg = render_whatsapp_message(
            tmpl_text,
            agent_name=agent.fullname,
            referral_link=referral_url,
            profile_link=profile_url,
            digital_price=dig_price,
            professional_price=prof_price
        )
        whatsapp_languages[lang_code] = {
            'language_code': lang_code,
            'label': lang_data.get('label', lang_code),
            'rendered_message': rendered_msg,
            'whatsapp_url': get_whatsapp_share_url(rendered_msg)
        }

    # Slab stats
    all_slabs = ChampionshipRewardSlab.objects.filter(campaign=campaign, is_active=True).order_by('threshold')
    from apps.referral_championship.services.reward_engine import get_reward_image
    slab_stats_api = []
    for s in all_slabs:
        achieved_count = ChampionshipParticipant.objects.filter(
            campaign=campaign,
            qualifying_referrals_count__gte=s.threshold
        ).count()
        slab_img_path = get_reward_image(s.reward_type, s.threshold)
        slab_stats_api.append({
            'id': s.id,
            'name': s.title,
            'threshold': s.threshold,
            'reward_type': s.reward_type,
            'value': float(s.value) if s.value is not None else None,
            'value_label': format_inr(s.value),
            'achieved_count': achieved_count,
            'seats_left': max(0, (s.winner_limit or 9999) - achieved_count) if s.winner_limit else None,
            'image_url': build_safe_absolute_uri(request, f"/static/{slab_img_path}")
        })

    # Claims & Draws
    my_claims = ChampionshipRewardClaim.objects.filter(participant=participant).select_related('reward_slab').order_by('-created_at')
    my_claims_api = []
    for c in my_claims:
        my_claims_api.append({
            'claim_id': c.id,
            'slab_id': c.reward_slab.id,
            'slab_title': c.reward_slab.title,
            'slab_threshold': c.reward_slab.threshold,
            'value_formatted': format_inr(c.reward_slab.value),
            'status': c.status,
            'voucher_code': c.voucher_code or None,
            'courier_name': c.courier_name or None,
            'tracking_number': c.tracking_number or None,
            'claimed_at': c.created_at.isoformat() if c.created_at else None,
        })

    draws_api = [
        {
            'tier': 1,
            'prize_name': 'Gold & Tech Goodies',
            'eligibility': '50+ referrals',
            'winner_count': 5,
            'draw_date': '2026-11-05',
            'is_ticket_active': qualified_count >= 50
        },
        {
            'tier': 2,
            'prize_name': 'Domestic Trip Upgrade',
            'eligibility': '100+ referrals',
            'winner_count': 3,
            'draw_date': '2026-11-05',
            'is_ticket_active': qualified_count >= 100
        },
        {
            'tier': 3,
            'prize_name': 'Mega International Luxury Draw',
            'eligibility': '200+ referrals',
            'winner_count': 1,
            'draw_date': '2026-11-05',
            'is_ticket_active': qualified_count >= 200
        },
    ]

    # Next Rank Needed
    next_rank_needed = 1
    if participant.current_rank and participant.current_rank > 1:
        prev_participant = ChampionshipParticipant.objects.filter(
            campaign=campaign,
            current_rank=participant.current_rank - 1
        ).first()
        if prev_participant:
            diff = prev_participant.qualifying_referrals_count - participant.qualifying_referrals_count
            next_rank_needed = max(1, diff + 1)

    # Roadmap formatted with absolute image URLs
    roadmap_items_api = []
    for item in roadmap_data['roadmap']:
        slab_obj = item.get('slab')
        claim_obj = item.get('claim')
        roadmap_items_api.append({
            'index': item['index'],
            'slab_id': slab_obj.id if slab_obj else None,
            'threshold': item['threshold'],
            'title': item['title'],
            'description': item['description'],
            'value': item['value'],
            'value_formatted': item['value_formatted'],
            'reward_type': item['reward_type'],
            'image_path': item['image_path'],
            'image_url': build_safe_absolute_uri(request, f"/static/{item['image_path']}"),
            'is_reached': item['is_reached'],
            'is_unlocked': item['is_unlocked'],
            'is_current_target': item['is_current_target'],
            'progress_percent': item['progress_percent'],
            'referrals_needed': item['referrals_needed'],
            'status': item['status'],
            'can_claim': item['can_request'],
            'is_voucher': item['is_voucher'],
            'status_label': item['status_label'],
            'claim_url': build_safe_absolute_uri(request, reverse('championship:agent_claim_reward', kwargs={'slab_id': slab_obj.id})) if slab_obj else None,
            'claim_details': {
                'claim_id': claim_obj.id if claim_obj else None,
                'status': claim_obj.status if claim_obj else None,
                'voucher_code': claim_obj.voucher_code if claim_obj else None,
            } if claim_obj else None
        })

    # Leaderboard entries
    top_50_api = []
    for r in top_50:
        top_50_api.append({
            'rank': r['rank'],
            'id': r['id'],
            'name': r['name'],
            'city': r.get('city', ''),
            'referrals': r['referrals'],
            'is_current_user': (r['id'] == participant.id)
        })

    top_10_api = [
        {
            'rank': r['rank'],
            'id': r['id'],
            'name': r['name'],
            'city': r.get('city', ''),
            'referrals': r['referrals']
        } for r in top_10
    ]

    hero_banner = {
        'campaign_id': campaign.id,
        'name': campaign.name,
        'status': campaign.status,
        'start_date': campaign.start_date.isoformat() if hasattr(campaign, 'start_date') and campaign.start_date else None,
        'end_date': campaign.end_date.isoformat() if hasattr(campaign, 'end_date') and campaign.end_date else None,
        'days_left': getattr(campaign, 'days_left', 0),
        'hero_image_url': build_safe_absolute_uri(request, '/static/championship/championship-hero.jpg'),
        'user_rank': participant.current_rank,
        'verified_referrals': qualified_count,
        'total_contenders': agg_stats.get('total_participants', 0),
        'referral_id': funnel['display_referral_id'],
        'referral_url': referral_url,
        'default_whatsapp_text': default_wa_text,
        'default_whatsapp_url': default_wa_url,
        'event_referral_mode': funnel.get('event_referral_mode', False),
    }

    access_gate = {
        'is_unlocked': is_unlocked,
        'profile_completion_percent': completion,
        'min_profile_percent': min_profile,
        'profile_satisfied': profile_satisfied,
        'review_count': review_count,
        'min_reviews': min_reviews,
        'reviews_satisfied': reviews_satisfied,
        'complete_profile_url': build_safe_absolute_uri(request, reverse('agents:agent_edit_profile')),
        'collect_reviews_profile_url': review_url,
        'collect_reviews_url': review_url,
        'review_url': review_url,
    }

    pipeline = {
        'invited_count': invited_count,
        'form_filled_count': form_filled_count,
        'paid_count': paid_count,
        'qualified_count': qualified_count,
        'target_qualified': funnel.get('referrals_target') or 5,
    }

    championship_road = {
        'milestones': roadmap_items_api,
        'next_reward_title': roadmap_data['next_reward'],
        'referrals_needed_for_next_reward': roadmap_data['referrals_needed']
    }

    conv_rate = round((qualified_count / invited_count * 100), 1) if invited_count > 0 else 0.0
    form_filled_pct = round((form_filled_count / invited_count * 100), 1) if invited_count > 0 else 0.0
    paid_pct = round((paid_count / invited_count * 100), 1) if invited_count > 0 else 0.0
    qual_pct = round((qualified_count / invited_count * 100), 1) if invited_count > 0 else 0.0

    insights_analytics = {
        'reach': invited_count,
        'intent': form_filled_count,
        'payments': paid_count,
        'conversion_rate_percent': conv_rate,
        'funnel_percentages': {
            'reach': 100.0,
            'intent': form_filled_pct,
            'payments': paid_pct,
            'qualified': qual_pct
        },
        'recent_activity': recent_referrals_api
    }

    invite_studio = {
        'referral_id': funnel['display_referral_id'],
        'referral_url': referral_url,
        'qr_base64': qr_base64,
        'qr_download_url': qr_download_url,
        'quick_share': {
            'whatsapp_url': default_wa_url,
            'telegram_url': f"https://t.me/share/url?url={referral_url}&text={default_wa_text}",
            'email_url': f"mailto:?subject=Join%20PadosiAgent%20Championship&body={default_wa_text}",
            'sms_text': default_wa_text
        },
        'whatsapp_multi_lingual': whatsapp_languages,
        'pro_tips': [
            "Put the printed QR on your office visitor desk.",
            "Post your QR screenshot to WhatsApp status & stories.",
            "Share in insurance club and branch advisor meetings."
        ]
    }

    my_rewards_draws = {
        'my_claims': my_claims_api,
        'championship_draws': draws_api
    }

    leaderboard = {
        'aggregate_stats': {
            'total_participants': agg_stats.get('total_participants', 0),
            'total_qualified': agg_stats.get('total_qualified', 0)
        },
        'top_3_podium': {
            'rank_1': top_10_api[0] if len(top_10_api) >= 1 else None,
            'rank_2': top_10_api[1] if len(top_10_api) >= 2 else None,
            'rank_3': top_10_api[2] if len(top_10_api) >= 3 else None
        },
        'user_position': {
            'user_rank': participant.current_rank,
            'verified_referrals': qualified_count,
            'next_rank_needed': next_rank_needed
        },
        'top_50': top_50_api
    }

    return {
        'success': True,
        'campaign_hero': hero_banner,
        'unlock_access_gate': access_gate,
        'referral_pipeline': pipeline,
        'championship_road': championship_road,
        'slab_pulse_board': slab_stats_api,
        'insights_analytics': insights_analytics,
        'invite_studio': invite_studio,
        'my_rewards_draws': my_rewards_draws,
        'leaderboard': leaderboard
    }


def agent_championship_dashboard_api(request):
    """
    Dedicated JSON API Endpoint for Agent Championship Dashboard.
    GET /agent/championship/api/agent/dashboard/
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse({'success': False, 'message': 'Agent account required'}, status=403)

    try:
        data = build_championship_dashboard_json_payload(request, agent)
        return JsonResponse(data)
    except Exception as e:
        logger.exception(f"Error serving agent championship dashboard API: {e}")
        return JsonResponse({'success': False, 'message': 'Internal Server Error'}, status=500)


def agent_championship_dashboard(request):
    """
    Agent Referral Championship Dashboard:
    - Verifies unlock gate: Profile completion >= 80% AND Reviews >= 10.
    - If locked: Renders unlock progress meters.
    - If unlocked: Full Championship Command Center with live stats, funnel, roadmap, WhatsApp share, and leaderboard.
    - Supports JSON API response when format=json or Accept: application/json header is provided.
    """
    if not request.user.is_authenticated:
        if request.GET.get('format') == 'json' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)
        return redirect('agents:agent_login')

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        if request.GET.get('format') == 'json' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'success': False, 'message': 'Agent account required'}, status=403)
        messages.error(request, "Please log in with your agent account.")
        return redirect('agents:agent_login')

    if request.GET.get('format') == 'json' or 'application/json' in request.headers.get('Accept', ''):
        try:
            data = build_championship_dashboard_json_payload(request, agent)
            return JsonResponse(data)
        except Exception as e:
            logger.exception(f"Error building json payload: {e}")
            return JsonResponse({'success': False, 'message': 'Internal Server Error'}, status=500)

    try:
        campaign = ChampionshipCampaign.get_current()
        participant = get_or_create_participant(agent, campaign)

        # ── Unlock Gate Requirements ──
        completion = profile_completion_percent(agent)
        review_count = agent_review_count(agent)

        is_unlocked, min_profile, min_reviews = _resolve_championship_unlock_gate(
            agent, campaign, participant, completion, review_count,
        )

        funnel = _referral_funnel_for_dashboard(request, agent, participant)
        invited_count = funnel['invited_count']
        form_filled_count = funnel['form_filled_count']
        paid_count = funnel['paid_count']
        qualified_count = funnel['qualified_count']
        referral_url = funnel['referral_url']
        recent_referrals = funnel['recent_referrals']

        # ── Roadmap & Next Reward ──
        roadmap_data = get_participant_roadmap(participant)

        qr_base64 = generate_qr_base64(referral_url)

        # ── Leaderboard Data ──
        top_10 = get_leaderboard_data(campaign, limit=10)
        top_50 = get_leaderboard_data(campaign, limit=50)
        agg_stats = get_campaign_aggregate_stats(campaign)

        # WhatsApp default message
        pricing = campaign.pricing_config if isinstance(campaign.pricing_config, dict) else {}
        dig_price_raw = (pricing.get('digital') or {}).get('campaign_price', 999) if isinstance(pricing.get('digital'), dict) else 999
        prof_price_raw = (pricing.get('professional') or {}).get('campaign_price', 4999) if isinstance(pricing.get('professional'), dict) else 4999
        try:
            dig_price = int(dig_price_raw or 999)
        except (TypeError, ValueError):
            dig_price = 999
        try:
            prof_price = int(prof_price_raw or 4999)
        except (TypeError, ValueError):
            prof_price = 4999

        profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else getattr(agent, 'profile', None)
        agent_slug_val = (getattr(profile, 'slug', None) if profile else None) or getattr(agent, 'agent_slug', None) or str(getattr(agent, 'id', ''))
        state_code = getattr(agent, 'state_code', 'gj')
        if callable(state_code):
            state_code = state_code()
        state_code = str(state_code or 'gj').strip().lower()
        profile_url = build_safe_absolute_uri(request, f"/{state_code}/{agent_slug_val}/")
        review_url = f"https://www.padosiagent.com/review/{agent_slug_val}/"

        default_wa_text = render_whatsapp_message(
            WHATSAPP_TEMPLATES['en']['templates'][0]['text'],
            agent_name=agent.fullname,
            referral_link=referral_url,
            profile_link=profile_url,
            digital_price=dig_price,
            professional_price=prof_price
        )
        default_wa_url = get_whatsapp_share_url(default_wa_text)

        # ── Slab Pulse Board Stats (How many participants have achieved each slab) ──
        all_slabs = ChampionshipRewardSlab.objects.filter(campaign=campaign, is_active=True).order_by('threshold')
        slab_stats = []
        for s in all_slabs:
            achieved_count = ChampionshipParticipant.objects.filter(
                campaign=campaign,
                qualifying_referrals_count__gte=s.threshold
            ).count()
            slab_stats.append({
                'slab': s,
                'id': s.id,
                'name': s.title,
                'threshold': s.threshold,
                'reward_type': s.reward_type,
                'value_label': format_inr(s.value),
                'achieved': achieved_count,
                'seats_left': max(0, (s.winner_limit or 9999) - achieved_count) if s.winner_limit else None,
            })

        # ── User Claims & Draws ──
        my_claims = ChampionshipRewardClaim.objects.filter(participant=participant).select_related('reward_slab').order_by('-created_at')
        draws = [
            {'tier': 1, 'prize_name': 'Gold & Tech Goodies', 'eligibility': '50+ referrals', 'winner_count': 5, 'draw_date': '2026-11-05'},
            {'tier': 2, 'prize_name': 'Domestic Trip Upgrade', 'eligibility': '100+ referrals', 'winner_count': 3, 'draw_date': '2026-11-05'},
            {'tier': 3, 'prize_name': 'Mega International Luxury Draw', 'eligibility': '200+ referrals', 'winner_count': 1, 'draw_date': '2026-11-05'},
        ]
        # ── Calculate referrals to beat next rank ──
        next_rank_needed = 1
        if participant.current_rank and participant.current_rank > 1:
            prev_participant = ChampionshipParticipant.objects.filter(
                campaign=campaign,
                current_rank=participant.current_rank - 1
            ).first()
            if prev_participant:
                diff = prev_participant.qualifying_referrals_count - participant.qualifying_referrals_count
                next_rank_needed = max(1, diff + 1)

        context = {
            'campaign': campaign,
            'agent': agent,
            'participant': participant,
            'completion': completion,
            'review_count': review_count,
            'min_profile': min_profile,
            'min_reviews': min_reviews,
            'is_unlocked': is_unlocked,
            'days_left': getattr(campaign, 'days_left', 0),
            'invited_count': invited_count,
            'form_filled_count': form_filled_count,
            'paid_count': paid_count,
            'qualified_count': qualified_count,
            'roadmap': roadmap_data['roadmap'],
            'next_reward': roadmap_data['next_reward'],
            'referrals_needed': roadmap_data['referrals_needed'],
            'referral_url': referral_url,
            'profile_url': profile_url,
            'review_url': review_url,
            'collect_reviews_profile_url': review_url,
            'collect_reviews_url': review_url,
            'qr_base64': qr_base64,
            'top_10': top_10,
            'top_50': top_50,
            'agg_stats': agg_stats,
            'next_rank_needed': next_rank_needed,
            'slab_stats': slab_stats,
            'my_claims': my_claims,
            'draws': draws,
            'recent_referrals': recent_referrals,
            'whatsapp_templates_json': json.dumps(WHATSAPP_TEMPLATES),
            'default_wa_url': default_wa_url,
            'default_wa_text': default_wa_text,
            'dig_price': dig_price,
            'prof_price': prof_price,
            'hide_footer': True,
            'hide_chatbot': True,
            'event_referral_mode': funnel.get('event_referral_mode', False),
            'event_referral_participant': funnel.get('event_referral_participant'),
            'event_referral_all': funnel.get('event_referral_all', []),
            'display_referral_id': funnel.get('display_referral_id', participant.referral_id),
            'referrals_target': funnel.get('referrals_target'),
        }
        return render(request, 'referral_championship/agent_dashboard.html', context)
    except Exception as e:
        logger.exception(f"Error loading agent championship dashboard: {e}")
        messages.error(request, "Unable to load championship dashboard right now. Please try again.")
        return redirect('agents:agent_dashboard')



@require_POST
def claim_reward_ajax(request, slab_id):
    """Handle claiming of rewards (e.g. Amazon vs Flipkart vouchers)."""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return JsonResponse({'success': False, 'message': 'Agent not found'}, status=404)

    campaign = ChampionshipCampaign.get_current()
    participant = get_object_or_404(ChampionshipParticipant, agent=agent, campaign=campaign)
    slab = get_object_or_404(ChampionshipRewardSlab, id=slab_id, campaign=campaign)

    if participant.is_fraud_blocked:
        return JsonResponse({'success': False, 'message': 'Your championship account is under review. Please contact support.'}, status=403)
    if not slab_is_claimable(slab):
        return JsonResponse({'success': False, 'message': 'This reward cannot be claimed here.'}, status=400)
    if participant.qualifying_referrals_count < slab.threshold:
        return JsonResponse({'success': False, 'message': 'Referral threshold not yet reached.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    voucher_pref = str(data.get('voucher_provider') or 'amazon').strip().lower()[:20]
    if voucher_pref not in ('amazon', 'flipkart'):
        voucher_pref = 'amazon'
    address = str(data.get('shipping_address') or '').strip()[:500]
    note = str(data.get('note') or '').strip()[:500]

    from django.db import transaction
    with transaction.atomic():
        claim, _ = ChampionshipRewardClaim.objects.select_for_update().get_or_create(
            participant=participant,
            reward_slab=slab,
            defaults={'status': 'processing'}
        )
        # A claim can be submitted, or its details updated, only until the team
        # acts on it; re-submitting after approval/dispatch duplicated rewards.
        if claim.status not in CLAIM_EDITABLE_STATUSES:
            return JsonResponse({
                'success': False,
                'message': f'This reward is already {claim.get_status_display().lower()}. Please contact support for changes.',
                'status': claim.status,
            }, status=409)

        claim.status = 'processing'
        claim_data = dict(claim.claim_data) if isinstance(claim.claim_data, dict) else {}
        claim_data.update({
            'shipping_address': address,
            'note': note,
            'claimed_at': timezone.now().isoformat(),
            'referrals_at_claim': participant.qualifying_referrals_count,
            'agent_name': agent.fullname or '',
            'agent_mobile': agent.mobile or '',
            'agent_email': agent.email or '',
        })
        if slab.reward_type in VOUCHER_REWARD_TYPES:
            claim_data['voucher_provider'] = voucher_pref
        claim.claim_data = claim_data
        claim.save()

    return JsonResponse({
        'success': True,
        'message': f'Your request for "{slab.title}" has been received. {CLAIM_CONTACT_MESSAGE}',
        'status': 'processing'
    })


def download_qr_code(request):
    """Direct PNG download of agent's branded championship QR code."""
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized', status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return HttpResponse('Agent not found', status=404)

    from apps.event_referral.services.championship_dashboard import event_referral_qr_join_url
    from apps.event_referral.services.participant_service import get_participant_for_agent

    participant = get_or_create_participant(agent)
    evt_p = get_participant_for_agent(agent)
    referral_url = event_referral_qr_join_url(
        request, agent, lambda path: build_safe_absolute_uri(request, path),
    )
    if not referral_url:
        domain = request.get_host()
        scheme = 'https' if request.is_secure() else 'http'
        referral_url = f"{scheme}://{domain}/agent-registration/join/{participant.referral_id}/"
        code_label = participant.referral_id
    else:
        code_label = evt_p.referral_code if evt_p else participant.referral_id

    qr_bytes = generate_qr_bytes(referral_url)
    response = HttpResponse(qr_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="PadosiAgent_QR_{code_label}.png"'
    return response
