"""Agent portal access control — payment required before dashboard routes."""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from apps.agents.services.account_auth import (
    agent_can_access_dashboard,
    resolve_agent_for_user,
)

# Agent-only routes that require a captured payment (subscription or paid invoice).
_PAID_AGENT_PATH_PREFIXES = (
    '/agent/dashboard/',
    '/agent/edit-profile/',
    '/agent/update-profile/',
    '/agent/referral/',
    '/agent/referral-info/',
    '/agent/upgrade-plan/',
    '/agent/leads/',
    '/agent/update-visibility/',
    '/agent/push-token/',
)


class AgentPaymentGateMiddleware:
    """
    Block unpaid agents from agent portal pages even if they are logged in.
    Payment verification runs in login/dashboard views; this middleware enforces
    the result on every protected /agent/* request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = (request.path or '').lower()
        if not any(path.startswith(prefix) for prefix in _PAID_AGENT_PATH_PREFIXES):
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        if getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False):
            return self.get_response(request)

        try:
            agent = resolve_agent_for_user(user)
        except Exception:
            agent = None

        if agent and not agent_can_access_dashboard(agent):
            messages.warning(
                request,
                'Please complete your payment to access the agent dashboard.',
            )
            return redirect(reverse('agents:chooseplan'))

        return self.get_response(request)
