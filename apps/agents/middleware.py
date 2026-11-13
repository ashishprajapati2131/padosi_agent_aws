"""Agent portal access control — payment required before dashboard routes."""
from django.contrib import messages
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from apps.agents.services.account_auth import (
    agent_can_access_dashboard,
    resolve_agent_for_user,
)
from apps.agents.services.agent_access import (
    RESTRICTED_LOGIN_MESSAGE,
    agent_is_admin_restricted,
)
from apps.home.services.portal_messages import PORTAL_AGENT, portal_error

# Agent-only routes that require a captured payment (subscription or paid invoice).
_PAID_AGENT_PATH_PREFIXES = (
    '/agent/dashboard/',
    '/agent/edit-profile/',
    '/agent/update-profile/',
    '/agent/referral/',
    '/agent/referral-info/',
    '/agent/upgrade-plan/',
    '/agent/leads/update-status/',
    '/agent/update-visibility/',
    '/agent/push-token/',
    # Paid dashboard features (generate-bio also spends LLM credits per call).
    '/agent/generate-bio/',
    '/agent/api/',
    '/agent/gbp/',
    '/agent/qr/',
    '/agent/career-timeline/',
    '/agent/review-card/',
)

# Gated paths called via fetch/AJAX that expect JSON.
_JSON_API_PREFIXES = (
    '/agent/generate-bio/',
    '/agent/api/',
    '/agent/career-timeline/',
    '/agent/gbp/status/',
    '/agent/gbp/save-url/',
)

# Signed-in agent pages. A restricted agent is logged out here, including the
# payment pages, so an open session cannot keep using the portal.
_RESTRICTION_PORTAL_PREFIXES = (
    '/agent/',
    '/agent-',
    '/chooseplan',
    '/payment-',
    '/forgot-password',
    '/reset-password',
    '/plan-',
    '/exclusive-plan',
    '/register/',
    '/quick-registration',
    '/agent-register',
    '/agent-registration',
    '/agent-check-',
    '/welcome-preview',
)


def _restriction_portal_path(path):
    if path.startswith(('/agent-login', '/agent-logout', '/logout')):
        return False
    return any(path.startswith(prefix) for prefix in _RESTRICTION_PORTAL_PREFIXES)


class AgentPaymentGateMiddleware:
    """
    Block unpaid agents from agent portal pages even if they are logged in.
    Payment verification runs in login/dashboard views; this middleware enforces
    the result on every protected /agent/* request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _restricted_agent(self, request):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return None
        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return None
        try:
            agent = resolve_agent_for_user(user)
            if not agent and getattr(user, 'email', None):
                from apps.agents.services.account_auth import find_agent
                agent = find_agent(user.email)
        except Exception:
            return None
        if agent and agent_is_admin_restricted(agent):
            return agent
        return None

    def __call__(self, request):
        path = (request.path or '').lower()
        restricted = self._restricted_agent(request)
        if restricted is not None:
            if path.startswith('/agent-login'):
                logout(request)
                if request.method == 'GET':
                    portal_error(request, RESTRICTED_LOGIN_MESSAGE, PORTAL_AGENT)
            elif _restriction_portal_path(path):
                logout(request)
                wants_json = (
                    path.startswith(_JSON_API_PREFIXES)
                    or request.headers.get('x-requested-with') == 'XMLHttpRequest'
                )
                if wants_json:
                    return JsonResponse({
                        'status': 'error',
                        'success': False,
                        'message': RESTRICTED_LOGIN_MESSAGE,
                    }, status=403)
                portal_error(request, RESTRICTED_LOGIN_MESSAGE, PORTAL_AGENT)
                return redirect(reverse('agents:agent_login'))

        if path.startswith('/agent/leads/capture/'):
            return self.get_response(request)

        if not any(path.startswith(prefix) for prefix in _PAID_AGENT_PATH_PREFIXES):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return self.get_response(request)

        try:
            agent = resolve_agent_for_user(user)
            if not agent and getattr(user, 'email', None):
                from apps.agents.services.account_auth import find_agent
                agent = find_agent(user.email)
        except Exception:
            agent = None

        if not agent or not agent_can_access_dashboard(agent):
            # AJAX/JSON feature endpoints get a JSON answer the page JS can
            # show, instead of a redirect to an HTML page. (Older gated paths
            # keep their original redirect behaviour.)
            if path.startswith(_JSON_API_PREFIXES):
                return JsonResponse({
                    'status': 'error',
                    'success': False,
                    'message': 'Please complete your payment to use this feature.',
                    'redirect': reverse('agents:chooseplan'),
                }, status=403)
            messages.warning(
                request,
                'Please complete your payment to access the agent dashboard.',
            )
            return redirect(reverse('agents:chooseplan'))

        return self.get_response(request)


class BackgroundJobsMiddleware:
    """After each response, start any scheduled job that is due (invoice
    retry, Paldi expirations). Replaces cron on this host; see
    apps/agents/services/background_jobs.py."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            from apps.agents.services.background_jobs import maybe_run_due_jobs
            maybe_run_due_jobs()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Background job trigger failed')
        return response
