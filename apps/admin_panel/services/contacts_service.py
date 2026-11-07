"""Write flows for the admin contact inbox / support tickets (views/contacts.py)."""

from django.utils.html import escape
import datetime
import logging

from apps.admin_panel.models.contact_reply import ContactReply

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.contacts")


def set_status(sub, status):
    sub.status = status
    sub.save(update_fields=["status", "updated_at"])


def delete_submission(sub):
    sub.delete()


def assign(sub, target_id):
    """target_id=None unassigns; caller has already validated the admin exists."""
    sub.assigned_admin_id = target_id
    sub.save(update_fields=["assigned_admin_id", "updated_at"])


def set_priority(sub, priority):
    sub.priority = priority
    sub.save(update_fields=["priority", "updated_at"])


def add_reply(sub, admin_id, admin_name, message, is_internal, want_email):
    """Optionally email the customer, save the reply, bump the ticket. Returns emailed."""
    emailed = False
    # Only customer-facing replies can be emailed (never internal notes).
    if want_email and not is_internal and sub.email:
        try:
            from apps.agents.services.brevo import email_service

            html = (
                # Name/subject come from the public contact form: escape (phishing HTML otherwise).
                f"<p>Hi {escape(sub.name)},</p>"
                f"<p>{escape(message).replace(chr(10), '<br>')}</p>"
                f"<p>Regarding your query <b>{escape(sub.reference_id or ('#' + str(sub.id)))}</b>: "
                f"{escape(sub.subject)}</p>"
                f"<p>— PadosiAgent Support</p>"
            )
            emailed = bool(
                email_service.send_generic(
                    sub.email, sub.name, f"Re: {sub.subject}", html
                )
            )
        except Exception as exc:
            # Never let an email failure break saving the reply.
            logger.error("Contact reply email failed for ticket %s: %s", sub.id, exc)
            emailed = False

    ContactReply.objects.create(
        submission=sub,
        admin_id=admin_id,
        admin_name=admin_name,
        message=message,
        is_internal_note=is_internal,
        emailed=emailed,
    )

    # A customer-facing reply moves an open ticket to 'replied'.
    update_fields = ["last_reply_at", "updated_at"]
    sub.last_reply_at = datetime.datetime.now()
    if not is_internal and sub.status not in ("closed",):
        sub.status = "replied"
        update_fields.append("status")
    sub.save(update_fields=update_fields)
    return emailed
