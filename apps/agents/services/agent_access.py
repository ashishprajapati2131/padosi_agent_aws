"""Admin activate / deactivate.

One flag is the source of truth. Workflow status is also set to ``suspended``
so older queries that only know that word keep hiding the agent. Payment and
event code must not clear the flag or move ``status`` off ``suspended``.
"""
import datetime
import logging

from django.db import connection

logger = logging.getLogger(__name__)

RESTRICTED_LOGIN_MESSAGE = (
    "You are restricted by the admin. For more information, contact the Padosi Agent team."
)

# Statuses the old list switch and the Manage Deactivate button already wrote.
# Rows in these states are restricted even before ``admin_restricted`` was set.
_RESTRICTED_STATUSES = ("suspended", "inactive")


def agent_is_admin_restricted(agent):
    """True when an admin has turned this agent off, including legacy rows."""
    if not agent:
        return False
    if bool(getattr(agent, "admin_restricted", False)):
        return True
    return (getattr(agent, "status", "") or "") in _RESTRICTED_STATUSES


def agent_is_publicly_listed(agent):
    """Find-agents, profile, card and QR. Card visibility and expiry are extra filters."""
    if not agent or agent_is_admin_restricted(agent):
        return False
    if bool(getattr(agent, "is_blacklisted", False)):
        return False
    return (getattr(agent, "status", "") or "") == "active"


def freeze_status_if_restricted(agent, new_status):
    """Keep a restricted agent suspended when some other flow would change status."""
    if agent_is_admin_restricted(agent):
        return "suspended"
    return new_status


def deactivate_agent(agent):
    """Hide the agent and block sign-in. Remembers the workflow status to restore."""
    if (agent.status or "") not in _RESTRICTED_STATUSES:
        # ``inactive`` / ``suspended`` are the restriction itself. Saving those
        # would make Activate put the agent straight back into a blocked state.
        agent.status_before_restriction = agent.status or ""
    agent.admin_restricted = True
    agent.status = "suspended"
    agent.restricted_at = datetime.datetime.now()
    agent.save(
        update_fields=[
            "admin_restricted",
            "status_before_restriction",
            "status",
            "restricted_at",
            "updated_at",
        ]
    )
    revoke_agent_api_tokens(agent)
    return agent


def activate_agent(agent):
    """Clear an admin restriction and restore the status from before it.

    A missing saved status becomes ``active`` only after a real captured
    payment. Otherwise the agent returns to ``pending_approval`` and stays
    off the public directory.
    """
    saved = (getattr(agent, "status_before_restriction", "") or "").strip()
    if saved and saved not in _RESTRICTED_STATUSES:
        restored = saved
    else:
        from apps.agents.services.account_auth import agent_has_completed_payment

        restored = "active" if agent_has_completed_payment(agent) else "pending_approval"
    agent.admin_restricted = False
    agent.status_before_restriction = ""
    agent.restricted_at = None
    agent.status = restored
    agent.save(
        update_fields=[
            "admin_restricted",
            "status_before_restriction",
            "restricted_at",
            "status",
            "updated_at",
        ]
    )
    return restored


def revoke_agent_api_tokens(agent):
    """End mobile-app sessions. Tokens are stored against the Laravel ``users`` id."""
    email = (getattr(agent, "email", "") or "").strip()
    if not email:
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE user_tokens
                SET is_revoked = 1
                WHERE user_id IN (
                    SELECT id FROM users WHERE LOWER(email) = LOWER(%s)
                )
                """,
                [email],
            )
    except Exception as exc:
        logger.warning(
            "Could not revoke API tokens for agent #%s: %s",
            getattr(agent, "pk", None),
            exc,
        )
