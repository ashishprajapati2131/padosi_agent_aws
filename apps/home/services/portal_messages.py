"""Scope Django flash messages to one login portal.

Admin, agent, distributor, and insurance share one browser session cookie.
A message queued on /admin/* must not render on /agent-login/, and success
vs error styling must follow the message level, not a strict tag equality check.
"""
from django.contrib import messages

PORTAL_ADMIN = 'admin'
PORTAL_AGENT = 'agent'
PORTAL_DISTRIBUTOR = 'distributor'
PORTAL_INSURANCE = 'insurance'

PORTALS = (PORTAL_ADMIN, PORTAL_AGENT, PORTAL_DISTRIBUTOR, PORTAL_INSURANCE)

_ADMIN_TEXT_MARKERS = (
    'admin panel',
    'staff account',
    'administrator accounts',
    'admin account not found',
)


def portal_tag(portal):
    return f'portal-{portal}'


def portal_error(request, text, portal):
    messages.error(request, text, extra_tags=portal_tag(portal))


def portal_success(request, text, portal):
    messages.success(request, text, extra_tags=portal_tag(portal))


def portal_warning(request, text, portal):
    messages.warning(request, text, extra_tags=portal_tag(portal))


_AUTH_TEXT_MARKERS = (
    'logged out',
    'login',
    'password',
    'credentials',
    'gated area',
    'valid login',
    'reset',
    'too many login',
    'enter both email',
    'account is currently',
    'account type',
    'temporarily unavailable',
    'unauthorized',
)


def message_is_for_portal(message, portal):
    tags = message.tags or ''
    owned = [name for name in PORTALS if portal_tag(name) in tags]
    if owned:
        return portal in owned

    text = str(message).lower()
    if any(marker in text for marker in _ADMIN_TEXT_MARKERS):
        return portal == PORTAL_ADMIN
    if any(marker in text for marker in _AUTH_TEXT_MARKERS):
        return True
    return False


def message_is_success(message):
    return 'success' in (message.tags or '')
