import logging

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.event_referral.constants import PALDI_EVENT_NAME, PALDI_OG_TITLE
from apps.event_referral.services.og_meta import paldi_og_context
from apps.event_referral.services.public_leaderboard import get_public_leaderboard_payload

logger = logging.getLogger(__name__)


def _profile_photo_absolute(request, profile):
    try:
        rel = profile.profile_photo_url
        if not rel:
            return ''
        if str(rel).startswith(('http://', 'https://')):
            return rel
        return request.build_absolute_uri(rel)
    except Exception:
        return ''


@require_http_methods(['GET'])
def public_leaderboard(request):
    """
    Public live board for event stall screens — ranked by counted paid EV- referrals.
    """
    payload = get_public_leaderboard_payload(
        limit=50,
        photo_url_builder=lambda p: _profile_photo_absolute(request, p),
    )
    rows = payload.get('leaderboard') or []
    context = {
        **payload,
        'podium_first': rows[0] if len(rows) > 0 else None,
        'podium_second': rows[1] if len(rows) > 1 else None,
        'podium_third': rows[2] if len(rows) > 2 else None,
        'visible_rest': rows[3:15],
        'rest_agents': rows[3:],
        'paldi_event_name': PALDI_EVENT_NAME,
        'page_title': f'{PALDI_EVENT_NAME} Referral Leaderboard | PadosiAgent',
        'hide_site_nav': True,
        'hide_footer': True,
        'hide_chatbot': True,
        'hide_header': True,
        'kiosk_mode': request.GET.get('kiosk', '1') != '0',
        'show_full_list': request.GET.get('full', '0') == '1',
    }
    context.update(paldi_og_context(request))
    context['og_share_title'] = f'{PALDI_EVENT_NAME} Live Referral Leaderboard'
    context.setdefault('og_page_title', PALDI_OG_TITLE)
    return render(request, 'event_referral/public_leaderboard.html', context)
