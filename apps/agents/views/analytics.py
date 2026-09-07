"""
Profile Analytics AJAX endpoint for the Agent Dashboard.
Returns aggregated discovery, engagement, and trend data for the logged-in agent.
"""
import logging
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse

from apps.agents.models import AgentCardImpression, AgentProfileView, AgentSearchEvent

logger = logging.getLogger(__name__)


@login_required(login_url='/agent-login/')
def agent_analytics_data(request):
    """
    GET /agent/api/analytics/?period=30
    Returns JSON analytics data for the logged-in agent.
    """
    from apps.agents.services.account_auth import resolve_agent_for_user
    agent = resolve_agent_for_user(request.user)
    if not agent:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    try:
        period = int(request.GET.get('period', 30))
        if period not in (7, 30, 90):
            period = 30
    except (ValueError, TypeError):
        period = 30

    today = date.today()
    period_start = today - timedelta(days=period - 1)
    prev_start   = period_start - timedelta(days=period)
    prev_end     = period_start - timedelta(days=1)

    # ── Agent's pincode for matching search events ────────────────────────
    agent_pincode = getattr(agent, 'agent_pincode', None) or ''

    # ── Current period aggregates ─────────────────────────────────────────
    impressions_curr = AgentCardImpression.objects.filter(
        agent=agent,
        impression_date__gte=period_start,
        impression_date__lte=today,
    ).aggregate(total=Sum('impression_count'))['total'] or 0

    views_curr = AgentProfileView.objects.filter(
        agent=agent,
        view_date__gte=period_start,
        view_date__lte=today,
    ).aggregate(total=Sum('view_count'))['total'] or 0

    searches_curr = AgentSearchEvent.objects.filter(
        search_date__gte=period_start,
        search_date__lte=today,
        pincode=agent_pincode if agent_pincode else None,
    ).aggregate(total=Sum('event_count'))['total'] or 0 if agent_pincode else 0

    # ── Previous period aggregates (for % change) ─────────────────────────
    impressions_prev = AgentCardImpression.objects.filter(
        agent=agent,
        impression_date__gte=prev_start,
        impression_date__lte=prev_end,
    ).aggregate(total=Sum('impression_count'))['total'] or 0

    views_prev = AgentProfileView.objects.filter(
        agent=agent,
        view_date__gte=prev_start,
        view_date__lte=prev_end,
    ).aggregate(total=Sum('view_count'))['total'] or 0

    searches_prev = AgentSearchEvent.objects.filter(
        search_date__gte=prev_start,
        search_date__lte=prev_end,
        pincode=agent_pincode if agent_pincode else None,
    ).aggregate(total=Sum('event_count'))['total'] or 0 if agent_pincode else 0

    # ── CTR calculation ───────────────────────────────────────────────────
    ctr_curr = round((views_curr / impressions_curr * 100), 1) if impressions_curr > 0 else 0.0
    ctr_prev = round((views_prev / impressions_prev * 100), 1) if impressions_prev > 0 else 0.0

    def pct_change(curr, prev):
        if prev == 0:
            return None  # No previous data — show neutral
        return round(((curr - prev) / prev) * 100, 1)

    # ── 30-day chart data (daily breakdown) ───────────────────────────────
    chart_labels     = []
    chart_impressions = []
    chart_views      = []
    chart_searches   = []

    # Index daily data
    imp_by_date = {
        row['impression_date']: row['total']
        for row in AgentCardImpression.objects.filter(
            agent=agent,
            impression_date__gte=period_start,
            impression_date__lte=today,
        ).values('impression_date').annotate(total=Sum('impression_count'))
    }
    views_by_date = {
        row['view_date']: row['total']
        for row in AgentProfileView.objects.filter(
            agent=agent,
            view_date__gte=period_start,
            view_date__lte=today,
        ).values('view_date').annotate(total=Sum('view_count'))
    }
    searches_by_date = {}
    if agent_pincode:
        searches_by_date = {
            row['search_date']: row['total']
            for row in AgentSearchEvent.objects.filter(
                pincode=agent_pincode,
                search_date__gte=period_start,
                search_date__lte=today,
            ).values('search_date').annotate(total=Sum('event_count'))
        }

    for i in range(period):
        day = period_start + timedelta(days=i)
        chart_labels.append(day.strftime('%d %b'))
        chart_impressions.append(imp_by_date.get(day, 0))
        chart_views.append(views_by_date.get(day, 0))
        chart_searches.append(searches_by_date.get(day, 0))

    # ── Top searched pincodes ─────────────────────────────────────────────
    top_pincodes_qs = AgentCardImpression.objects.filter(
        agent=agent,
        impression_date__gte=period_start,
        impression_date__lte=today,
        search_pincode__isnull=False,
    ).values('search_pincode').annotate(
        total=Sum('impression_count')
    ).order_by('-total')[:5]

    # Enrich with area names from Pincode table
    from apps.home.models import Pincode as PincodeModel
    pincode_area_map = {}
    pincode_values = [r['search_pincode'] for r in top_pincodes_qs if r['search_pincode']]
    for pc in PincodeModel.objects.filter(pincode__in=pincode_values):
        pincode_area_map[pc.pincode] = pc.formatted_location or pc.office_name or pc.pincode

    top_pincodes = [
        {
            'pincode': row['search_pincode'],
            'area': pincode_area_map.get(row['search_pincode'], row['search_pincode']),
            'count': row['total'],
        }
        for row in top_pincodes_qs
    ]

    # ── Quick Insight text ────────────────────────────────────────────────
    if impressions_curr == 0:
        insight = "Start getting discovered! Your profile analytics will appear here as people search for agents in your area."
    elif ctr_curr < 5:
        insight = f"Your click-through rate is {ctr_curr}%. Consider updating your profile photo and headline to attract more clicks."
    elif ctr_curr < 12:
        insight = f"Your click-through rate is {ctr_curr}% — close to average. A better photo or more reviews can push it higher."
    elif ctr_curr < 20:
        insight = f"Great engagement! Your click-through rate is {ctr_curr}%, which is above average."
    else:
        insight = f"Excellent! Your click-through rate is {ctr_curr}%. You are one of the most engaging profiles in your area."

    return JsonResponse({
        'success': True,
        'period': period,
        'summary': {
            'card_impressions':       impressions_curr,
            'card_impressions_prev':  impressions_prev,
            'card_impressions_change': pct_change(impressions_curr, impressions_prev),
            'profile_views':          views_curr,
            'profile_views_prev':     views_prev,
            'profile_views_change':   pct_change(views_curr, views_prev),
            'ctr':                    ctr_curr,
            'ctr_prev':               ctr_prev,
            'ctr_change':             pct_change(ctr_curr, ctr_prev),
            'pincode_searches':       searches_curr,
            'pincode_searches_prev':  searches_prev,
            'pincode_searches_change': pct_change(searches_curr, searches_prev),
        },
        'chart': {
            'labels':      chart_labels,
            'impressions': chart_impressions,
            'views':       chart_views,
            'searches':    chart_searches,
        },
        'top_pincodes': top_pincodes,
        'insight': insight,
    })
