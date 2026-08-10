"""
Favorite agents toggle — port of App\\Http\\Controllers\\Frontend\\FavoriteController
(routes/web.php:82 → POST /agent/toggle-favorite).

Unauthenticated users are blocked by the JS guest gate (quick-register popup);
this view re-checks auth as defense in depth and mirrors Laravel's 401 JSON.
Agent-role users are excluded server-side (Laravel's restrict.agent middleware).
"""

from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.agents.models import Agent, FavoriteAgent


@require_POST
def toggle_favorite(request):
    if not request.user.is_authenticated:
        return JsonResponse({
            'status': 'error',
            'message': 'Please login to favorite agents',
            'redirect': '/find-agents',
        }, status=401)

    if Agent.objects.filter(user=request.user).exists():
        return JsonResponse({
            'status': 'error',
            'message': 'Agents cannot save favourites.',
        }, status=403)

    agent_id = request.POST.get('agent_id')
    if not agent_id or not str(agent_id).isdigit():
        return JsonResponse({'status': 'error', 'message': 'Invalid agent.'}, status=400)
    if not Agent.objects.filter(id=agent_id).exists():
        return JsonResponse({'status': 'error', 'message': 'Agent does not exist.'}, status=400)

    favorite = FavoriteAgent.objects.filter(user=request.user, agent_id=agent_id).first()
    if favorite:
        favorite.delete()
        is_favorited = False
    else:
        try:
            FavoriteAgent.objects.create(user=request.user, agent_id=agent_id)
        except IntegrityError:
            return JsonResponse({'status': 'error', 'message': 'Agent does not exist.'}, status=400)
        is_favorited = True

    return JsonResponse({'status': 'success', 'is_favorited': is_favorited})