"""Write flows for the generic admin delete endpoint (views/delete.py).

Each handler takes the record id, performs the delete and returns the
pre-delete snapshot, or raises RecordNotFound / AgentSoftDeleted.
"""

import logging

from django.db import connection, transaction

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.delete")


class RecordNotFound(Exception):
    """Raised with the user-facing 404 message."""


class AgentSoftDeleted(Exception):
    """Agent kept with status 'deleted' because it has payment records."""

    def __init__(self, snapshot):
        super().__init__("soft-deleted")
        self.snapshot = snapshot


def delete_agent(record_id):
    with connection.cursor() as cursor:
        # 1. Fetch complete agent snapshot before deletion
        cursor.execute(
            """
                    SELECT id, user_id, email, fullname, mobile, status, plan_type, agent_pincode, profession
                    FROM agents WHERE id = %s
                """,
            [record_id],
        )
        agent_row = cursor.fetchone()
        if not agent_row:
            raise RecordNotFound("Record not found")

        agent_email = agent_row[2]
        cols_agent = [
            "id",
            "user_id",
            "email",
            "fullname",
            "mobile",
            "status",
            "plan_type",
            "agent_pincode",
            "profession",
        ]
        snapshot = dict(
            zip(cols_agent, [str(v) if v is not None else "" for v in agent_row])
        )

        # An agent with payment history is kept (status 'deleted'):
        # hard-deleting it with FK checks off orphaned its subscriptions
        # and invoices (needed for GST / refunds).
        from apps.agents.models import AgentSubscription, Invoice
        from apps.agents.services.account_auth import is_real_razorpay_id

        # A 'pending' row with a real order may hold a captured payment not yet reconciled;
        # deleting it makes that payment unfindable.
        order_ids = AgentSubscription.objects.filter(agent_id=record_id).values_list(
            "razorpay_order_id", flat=True
        )
        has_payments = (
            AgentSubscription.objects.filter(
                agent_id=record_id, payment_status__in=["completed", "refunded"]
            ).exists()
            or Invoice.objects.filter(agent_id=record_id).exists()
            or any(is_real_razorpay_id(o, "order_") for o in order_ids)
        )
        if has_payments:
            from apps.agents.models import Agent

            Agent.objects.filter(pk=record_id).update(status="deleted")
            if agent_email:
                cursor.execute(
                    "UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)",
                    [agent_email],
                )
            raise AgentSoftDeleted(snapshot)

        # 2-4 run in one transaction: a failed step leaves the agent untouched.
        with transaction.atomic():
            # 2. Backup agent record into agent_backup table
            try:
                cursor.execute(
                    """
                            INSERT INTO agent_backup (
                                id, user_id, event_id, distributor_id, fullname, email, google_id,
                                email_verified_at, mobile, registration_step, agent_pincode, latitude, longitude,
                                plan_type, trial_ends_at, upgrade_discount_percent, referred_by_code,
                                referral_reward_type, referral_reward_claimed, status, is_approved, approved_at,
                                badge, admin_notes, registration_draft, user_types, insurance_companies,
                                experience_range, client_base, achievement_photo_limit, profession, created_at, updated_at
                            )
                            SELECT
                                id, user_id, event_id, distributor_id, fullname, email, google_id,
                                email_verified_at, mobile, registration_step, agent_pincode, latitude, longitude,
                                plan_type, trial_ends_at, upgrade_discount_percent, referred_by_code,
                                referral_reward_type, referral_reward_claimed, status, is_approved, approved_at,
                                badge, admin_notes, registration_draft, user_types, insurance_companies,
                                experience_range, client_base, achievement_photo_limit, profession, created_at, updated_at
                            FROM agents WHERE id = %s
                            ON DUPLICATE KEY UPDATE
                                fullname = VALUES(fullname),
                                email = VALUES(email),
                                status = VALUES(status),
                                updated_at = NOW()
                        """,
                    [record_id],
                )
            except Exception as backup_err:
                # Never hard-delete without a backup: the row would be gone for good.
                logger.error(
                    f"Agent backup failed for agent {record_id}; delete aborted: {backup_err}"
                )
                raise

            # 3. Suspend linked user account. By email: agents.user_id is the
            # Django auth_user id, so "WHERE id = user_id" suspended whichever
            # person had that users id.
            if agent_email:
                cursor.execute(
                    "UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)",
                    [agent_email],
                )

            # 4. Delete the agent record with foreign key check guard
            cursor.execute("SET FOREIGN_KEY_CHECKS=0")
            try:
                cursor.execute(
                    "DELETE FROM registration_activity_logs WHERE agent_id = %s",
                    [record_id],
                )
                # No completed payments here: remove its unpaid checkout rows too.
                cursor.execute(
                    "DELETE FROM agent_subscriptions WHERE agent_id = %s", [record_id]
                )
                cursor.execute("DELETE FROM agents WHERE id = %s", [record_id])
            finally:
                cursor.execute("SET FOREIGN_KEY_CHECKS=1")
    return snapshot


def delete_agent_draft(record_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, fullname, email, mobile, agent_pincode FROM agent_drafts WHERE id = %s",
            [record_id],
        )
        draft_row = cursor.fetchone()
        if not draft_row:
            raise RecordNotFound("Draft not found")

        cols_draft = ["id", "fullname", "email", "mobile", "agent_pincode"]
        snapshot = dict(
            zip(cols_draft, [str(v) if v is not None else "" for v in draft_row])
        )

        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        try:
            cursor.execute(
                "DELETE FROM registration_activity_logs WHERE draft_id = %s",
                [record_id],
            )
            cursor.execute("DELETE FROM agent_drafts WHERE id = %s", [record_id])
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS=1")
    return snapshot


def delete_user(record_id):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, role, fullname, email, status FROM users WHERE id = %s",
            [record_id],
        )
        user_row = cursor.fetchone()
        if not user_row:
            raise RecordNotFound("Record not found")

        user_role = user_row[1]
        cols_user = ["id", "role", "fullname", "email", "status"]
        snapshot = dict(
            zip(cols_user, [str(v) if v is not None else "" for v in user_row])
        )

        if user_role == "distributor":
            # Distributor Deletion: Suspend the user and remove from Distributors module
            # by changing the role, ensuring they remain in the Users module.
            cursor.execute(
                "UPDATE users SET status = 'suspended' WHERE id = %s", [record_id]
            )
            cursor.execute(
                "UPDATE users SET role = 'client' WHERE id = %s", [record_id]
            )
        else:
            # Generic User hard-delete behavior
            cursor.execute("DELETE FROM users WHERE id = %s", [record_id])
    return snapshot


def delete_lead(record_id):
    snapshot = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, agent_id, name, phone, email, notes, created_at FROM agent_leads WHERE id = %s",
            [record_id],
        )
        lead_row = cursor.fetchone()
        if lead_row:
            cols_lead = [
                "id",
                "agent_id",
                "name",
                "phone",
                "email",
                "notes",
                "created_at",
            ]
            snapshot = dict(
                zip(cols_lead, [str(v) if v is not None else "" for v in lead_row])
            )
        cursor.execute("DELETE FROM agent_leads WHERE id = %s", [record_id])
    return snapshot


def delete_promo_code(record_id):
    snapshot = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, code, discount_type, discount_value, max_uses, times_used, is_active FROM promo_codes WHERE id = %s",
            [record_id],
        )
        promo_row = cursor.fetchone()
        if promo_row:
            cols_promo = [
                "id",
                "code",
                "discount_type",
                "discount_value",
                "max_uses",
                "times_used",
                "is_active",
            ]
            snapshot = dict(
                zip(cols_promo, [str(v) if v is not None else "" for v in promo_row])
            )
        cursor.execute("DELETE FROM promo_codes WHERE id = %s", [record_id])
    return snapshot


def delete_faq(record_id):
    snapshot = {}
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, question, answer, is_active FROM faqs WHERE id = %s",
            [record_id],
        )
        faq_row = cursor.fetchone()
        if faq_row:
            cols_faq = ["id", "question", "answer", "is_active"]
            snapshot = dict(
                zip(cols_faq, [str(v) if v is not None else "" for v in faq_row])
            )
        cursor.execute("DELETE FROM faqs WHERE id = %s", [record_id])
    return snapshot
