"""Write flows for the admin agent pages (views/agents.py)."""

import json
import logging

from django.core.cache import cache
from django.db import connection
from django.utils import timezone

from apps.agents.models import PaymentStatus

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.agents")


def after_status_change(agent_id, admin_id, ip_address, old_status, new_status):
    """Lead sync, edit log and WhatsApp notice once toggle_status has saved the status."""
    try:
        from apps.agents.models import Agent
        from apps.agents.services.registration_leads import sync_lead_for_agent

        agent_row = Agent.objects.filter(pk=agent_id).first()
        if agent_row:
            sync_lead_for_agent(agent_row)
    except Exception:
        logger.exception("Quick-registration lead sync failed after status change")

    # Log boundary change
    if new_status in ["active", "suspended", "rejected"]:
        step_label = "Status Changed by Admin"
        if new_status == "active":
            step_label = "Approved by Admin"
        elif new_status == "suspended":
            step_label = "Suspended by Admin"

        try:
            from ..models.agent_profile_edit_log import AgentProfileEditLog

            AgentProfileEditLog.objects.create(
                agent_id=int(agent_id),
                edited_by="admin",
                edited_by_id=admin_id,
                step=None,
                step_label=step_label,
                changes=json.dumps([]),
                ip_address=ip_address,
                status_before=old_status,
                status_after=new_status,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
        except Exception as e:
            # The status is already saved; failing here returned an error for
            # a change that had happened.
            logger.error("AUDIT LOG ERROR: %r", e)

    # Notify agent on WhatsApp if approved or rejected from pending_approval
    if old_status == "pending_approval":
        if new_status == "active":
            notify_approved_whatsapp(agent_id)
        elif new_status in ("suspended", "rejected"):
            try:
                from apps.wa_agent_bot.services.notification_service import (
                    notify_agent_rejected_whatsapp,
                )

                notify_agent_rejected_whatsapp(agent_id)
            except Exception as notify_err:
                logger.warning(
                    f"Failed to notify agent #{agent_id} rejection on WhatsApp: {notify_err}"
                )


def notify_approved_whatsapp(agent_id):
    try:
        from apps.wa_agent_bot.services.notification_service import (
            notify_agent_approved_whatsapp,
        )

        notify_agent_approved_whatsapp(agent_id)
    except Exception as notify_err:
        logger.warning(
            f"Failed to notify agent #{agent_id} approval on WhatsApp: {notify_err}"
        )


def bulk_approve_pending(agent_ids):
    """Approve the pending_approval agents among agent_ids.

    Returns (approved_ids, skipped, old_statuses); approved_ids is empty (and
    nothing was written) when none of them await approval.
    """
    with connection.cursor() as cursor:
        # Get existing statuses to log properly
        format_strings = ",".join(["%s"] * len(agent_ids))
        cursor.execute(
            f"SELECT id, status FROM agents WHERE id IN ({format_strings})",
            agent_ids,
        )
        rows = cursor.fetchall()
        old_statuses = {row[0]: row[1] for row in rows}

        # Bulk approve is for the approval queue only: an arbitrary id
        # list could activate unpaid or suspended agents.
        agent_ids = [
            str(aid) for aid, st in old_statuses.items() if st == "pending_approval"
        ]
        skipped = len(old_statuses) - len(agent_ids)
        if not agent_ids:
            return agent_ids, skipped, old_statuses
        format_strings = ",".join(["%s"] * len(agent_ids))

        # Update statuses
        cursor.execute(
            f"UPDATE agents SET status = 'active', is_approved = 1, approved_at = COALESCE(approved_at, %s) WHERE id IN ({format_strings})",
            [timezone.now()] + agent_ids,
        )
        cache.delete("homepage_reviews")
        try:
            from apps.agents.models import Agent
            from apps.agents.services.registration_leads import (
                sync_lead_for_agent,
            )

            for approved in Agent.objects.filter(pk__in=agent_ids):
                sync_lead_for_agent(approved)
        except Exception:
            logger.exception("Quick-registration lead sync failed after bulk approve")
    return agent_ids, skipped, old_statuses


def log_bulk_approvals(agent_ids, old_statuses, admin_id, ip_address):
    from ..models.agent_profile_edit_log import AgentProfileEditLog

    for aid in agent_ids:
        aid_int = int(aid)
        old_status = old_statuses.get(aid_int, "pending")
        AgentProfileEditLog.objects.create(
            agent_id=aid_int,
            edited_by="admin",
            edited_by_id=admin_id,
            step=None,
            step_label="Approved by Admin (Bulk)",
            changes=json.dumps([]),
            ip_address=ip_address,
            status_before=old_status,
            status_after="active",
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )


def update_badge(agent_id, badge_value):
    """Returns False when the agent does not exist."""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE agents SET badge = %s WHERE id = %s", [badge_value, agent_id]
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM agents WHERE id = %s", [agent_id])
            if not cursor.fetchone():
                return False
    return True


def update_irdai_license(agent_id, license_number):
    """Returns False when the agent does not exist."""
    with connection.cursor() as cursor:
        # Check if agent exists
        cursor.execute("SELECT id FROM agents WHERE id = %s", [agent_id])
        if not cursor.fetchone():
            return False

        # Check if agent profile exists
        cursor.execute("SELECT id FROM agent_profiles WHERE agent_id = %s", [agent_id])
        profile_exists = bool(cursor.fetchone())

        if profile_exists:
            cursor.execute(
                "UPDATE agent_profiles SET license_number = %s, updated_at = %s WHERE agent_id = %s",
                [license_number, timezone.now(), agent_id],
            )
        else:
            cursor.execute(
                "INSERT INTO agent_profiles (agent_id, license_number, created_at, updated_at) VALUES (%s, %s, %s, %s)",
                [agent_id, license_number, timezone.now(), timezone.now()],
            )
    return True


def save_agent_notes(agent_id, final_notes):
    """Returns False when the agent does not exist."""
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE agents SET admin_notes = %s WHERE id = %s",
            [final_notes, agent_id],
        )
        if cursor.rowcount == 0:
            cursor.execute("SELECT id FROM agents WHERE id = %s", [agent_id])
            if not cursor.fetchone():
                return False
    return True


def update_visibility(field, value, agent_id):
    """field must already be checked against the view's whitelist."""
    with connection.cursor() as cursor:
        # We construct the query safely using the whitelisted field string.
        query = f"UPDATE agent_profiles SET {field} = %s, updated_at = %s WHERE agent_id = %s"
        cursor.execute(query, [value, timezone.now(), agent_id])


def set_achievement_limit(agent_id, new_limit):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE agents SET achievement_photo_limit = %s, updated_at = %s WHERE id = %s",
            [new_limit, timezone.now(), agent_id],
        )


def apply_plan_change(agent_id, new_plan, plan_type):
    """Set the current subscription's plan and agents.plan_type; returns the old plan."""
    from datetime import timedelta
    from django.db import transaction
    from apps.agents.models import Agent, AgentSubscription

    with transaction.atomic():
        # Change the agent's current subscription only. Updating every row
        # rewrote the plan of all past payments (and their invoices).
        current = (
            AgentSubscription.objects.filter(agent_id=agent_id, status="active")
            .order_by("-created_at")
            .first()
            or AgentSubscription.objects.filter(agent_id=agent_id)
            .order_by("-created_at")
            .first()
        )
        old_plan = current.selected_plan if current else None
        if current:
            current.selected_plan = new_plan
            current.save(update_fields=["selected_plan", "updated_at"])
        elif new_plan:
            now = timezone.now()
            AgentSubscription.objects.create(
                agent_id=agent_id,
                selected_plan=new_plan,
                registration_amount=0,
                payment_status=PaymentStatus.COMPLETED,
                status="active",
                starts_at=now,
                expires_at=now + timedelta(days=365),
            )

        Agent.objects.filter(pk=agent_id).update(
            plan_type=plan_type, updated_at=timezone.now()
        )
    return old_plan


def set_review_approval(review_id, is_approved):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE agent_reviews SET is_approved = %s WHERE id = %s",
            [is_approved, review_id],
        )


def update_agent_profile(
    agent_id,
    previous_email,
    fullname,
    email,
    mobile,
    experience_range,
    address,
    office_address,
    license_number,
    pan_number,
    license_valid_till,
    arn_number,
    euin_number,
    investment_valid_till,
    investment_types,
):
    """Caller has validated the agent exists and the email is free."""
    from django.db import transaction
    from apps.agents.services.account_auth import sync_agent_email_change

    with transaction.atomic(), connection.cursor() as cursor:
        # Update agents table
        cursor.execute(
            """
                UPDATE agents
                SET fullname = %s, email = %s, mobile = %s, experience_range = %s, updated_at = %s
                WHERE id = %s
            """,
            [fullname, email, mobile, experience_range, timezone.now(), agent_id],
        )

        # Update agent_profiles table
        cursor.execute(
            """
                UPDATE agent_profiles
                SET address = %s, office_address = %s, license_number = %s, pan_number = %s, experience_years = %s,
                    license_valid_till = %s, arn_number = %s, euin_number = %s, investment_valid_till = %s, investment_types = %s,
                    updated_at = %s
                WHERE agent_id = %s
            """,
            [
                address,
                office_address,
                license_number,
                pan_number,
                experience_range,
                license_valid_till,
                arn_number,
                euin_number,
                investment_valid_till,
                json.dumps(investment_types),
                timezone.now(),
                agent_id,
            ],
        )
        # Keep users / auth_user on the same address or the agent can't log in.
        sync_agent_email_change(previous_email, email, fullname)
