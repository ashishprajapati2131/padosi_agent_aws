"""
career_timeline.py
──────────────────
Read-only API endpoint for auto-detected career timeline suggestions.

GET /agents/career-timeline/suggestions/
  • Requires the agent to be logged in (or admin session).
  • Returns JSON only — no DB writes.
  • Filters out suggestions whose key already appears in the agent's saved
    timelines via AgentCareerTimeline.suggestion_key (nullable CharField).

This view is intentionally isolated: it does not touch update_profile or any
other existing view.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

from apps.agents.models import Agent, AgentCareerTimeline
from apps.agents.services.career_timeline_suggestions import get_career_timeline_suggestions


@require_GET
@never_cache
def career_timeline_suggestions(request):
    """
    Returns auto-detected career timeline suggestions for the logged-in agent.

    Suggestions whose `key` matches an existing AgentCareerTimeline row's
    `suggestion_key` field are excluded (de-duplication).

    Response shape:
    {
        "status": "success",
        "suggestions": [
            {
                "key":         "career_start",
                "title":       "Started Insurance Career",
                "subtitle":    "Based on 12 years of experience — year auto-calculated",
                "event_type":  "Career",
                "month":       "",
                "year":        "2014",
                "source_field":"experience_years"
            },
            ...
        ]
    }
    """
    # ── Auth: support both regular agent session and admin-acting-as-agent ──
    from apps.admin_panel.views.dashboard import _get_admin_from_session
    admin_id = _get_admin_from_session(request)
    is_admin = bool(admin_id) or getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False)

    if not is_admin and not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Authentication required'}, status=401)

    # ── Resolve agent ───────────────────────────────────────────────────────
    agent_id = request.GET.get('agent_id')
    if is_admin and agent_id:
        agent = Agent.objects.filter(id=agent_id).first()
    else:
        agent = Agent.objects.filter(user=request.user).first()

    if not agent:
        return JsonResponse({'status': 'error', 'message': 'Agent not found'}, status=404)

    # ── Generate suggestions (pure function, no DB writes) ──────────────────
    all_suggestions = get_career_timeline_suggestions(agent)

    # ── De-duplication: exclude keys already saved in the agent's timelines ─
    # Reads `suggestion_key` column on agent_career_timelines.
    # If the column doesn't exist yet (pre-migration), the query falls back
    # gracefully and de-duplication is simply skipped.
    try:
        used_keys = set(
            AgentCareerTimeline.objects
            .filter(agent=agent)
            .exclude(suggestion_key__isnull=True)
            .exclude(suggestion_key='')
            .values_list('suggestion_key', flat=True)
        )
    except Exception:
        # Column hasn't been added yet — skip de-duplication safely
        used_keys = set()

    filtered = [s for s in all_suggestions if s['key'] not in used_keys]

    return JsonResponse({
        'status': 'success',
        'suggestions': filtered,
    })
