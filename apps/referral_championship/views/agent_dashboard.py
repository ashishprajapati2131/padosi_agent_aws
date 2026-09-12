import json
import logging
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
from apps.referral_championship.services.reward_engine import get_participant_roadmap, format_inr
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


def agent_championship_dashboard(request):
    """
    Agent Referral Championship Dashboard:
    - Verifies unlock gate: Profile completion >= 80% AND Reviews >= 10.
    - If locked: Renders unlock progress meters.
    - If unlocked: Full Championship Command Center with live stats, funnel, roadmap, WhatsApp share, and leaderboard.
    """
    if not request.user.is_authenticated:
        return redirect('agents:agent_login')

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        messages.error(request, "Please log in with your agent account.")
        return redirect('agents:agent_login')

    campaign = ChampionshipCampaign.get_current()
    participant = get_or_create_participant(agent, campaign)

    # ── Unlock Gate Requirements ──
    completion = profile_completion_percent(agent)
    review_count = agent_review_count(agent)

    unlock_cfg = campaign.unlock_config or {'min_profile_percent': 80, 'min_reviews': 10}
    min_profile = int(unlock_cfg.get('min_profile_percent', 80))
    min_reviews = int(unlock_cfg.get('min_reviews', 10))

    is_unlocked = (completion >= min_profile and review_count >= min_reviews)
    if is_unlocked and not participant.is_unlocked:
        participant.is_unlocked = True
        participant.profile_completed_at = timezone.now()
        participant.reviews_completed_at = timezone.now()
        participant.save(update_fields=['is_unlocked', 'profile_completed_at', 'reviews_completed_at'])

    # ── Funnel Metrics ──
    referrals_qs = ChampionshipReferral.objects.filter(referrer=participant)
    invited_count = referrals_qs.count()
    form_filled_count = referrals_qs.exclude(registration_state='started').count()
    paid_count = referrals_qs.filter(registration_state__in=['paid', 'active']).count()
    qualified_count = participant.qualifying_referrals_count

    # ── Roadmap & Next Reward ──
    roadmap_data = get_participant_roadmap(participant)

    # ── Referral Link & QR Code ──
    domain = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    referral_url = f"{scheme}://{domain}/join/{participant.referral_id}/"
    qr_base64 = generate_qr_base64(referral_url)

    # ── Leaderboard Data ──
    top_10 = get_leaderboard_data(campaign, limit=10)
    top_50 = get_leaderboard_data(campaign, limit=50)
    agg_stats = get_campaign_aggregate_stats(campaign)

    # WhatsApp default message
    pricing = campaign.pricing_config or {}
    dig_price = pricing.get('digital', {}).get('campaign_price', 999)
    prof_price = pricing.get('professional', {}).get('campaign_price', 4999)
    profile_url = f"{scheme}://{domain}/agent/{agent.agent_slug or agent.id}/"

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
    recent_referrals = referrals_qs.order_by('-created_at')[:20]

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
        'days_left': campaign.days_left,
        'invited_count': invited_count,
        'form_filled_count': form_filled_count,
        'paid_count': paid_count,
        'qualified_count': qualified_count,
        'roadmap': roadmap_data['roadmap'],
        'next_reward': roadmap_data['next_reward'],
        'referrals_needed': roadmap_data['referrals_needed'],
        'referral_url': referral_url,
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
    }
    return render(request, 'referral_championship/agent_dashboard.html', context)


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

    if participant.qualifying_referrals_count < slab.threshold:
        return JsonResponse({'success': False, 'message': 'Referral threshold not yet reached.'}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST

    voucher_pref = data.get('voucher_provider', 'amazon') # 'amazon' or 'flipkart'
    address = data.get('shipping_address', '')

    claim, _ = ChampionshipRewardClaim.objects.get_or_create(
        participant=participant,
        reward_slab=slab,
        defaults={'status': 'processing'}
    )

    claim.status = 'processing'
    claim.claim_data = {
        'voucher_provider': voucher_pref,
        'shipping_address': address,
        'claimed_at': timezone.now().isoformat()
    }
    claim.save()

    return JsonResponse({
        'success': True,
        'message': f'Reward claim for "{slab.title}" submitted successfully! Our team is processing your voucher/reward.',
        'status': 'processing'
    })


def download_qr_code(request):
    """Direct PNG download of agent's branded championship QR code."""
    if not request.user.is_authenticated:
        return HttpResponse('Unauthorized', status=401)

    agent = Agent.objects.filter(user=request.user).first()
    if not agent:
        return HttpResponse('Agent not found', status=404)

    participant = get_or_create_participant(agent)
    domain = request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    referral_url = f"{scheme}://{domain}/join/{participant.referral_id}/"

    qr_bytes = generate_qr_bytes(referral_url)
    response = HttpResponse(qr_bytes, content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="PadosiAgent_QR_{participant.referral_id}.png"'
    return response
