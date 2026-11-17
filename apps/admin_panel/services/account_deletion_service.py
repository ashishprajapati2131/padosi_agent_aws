"""Account deletion: immediate lock, admin Terminate/Activate, 30-day backup+purge."""

import gzip
import json
import logging
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from apps.agents.models import AccountDeletionRequest, Agent

# Same logger name as before the move, so log routing/filters are unchanged.
logger = logging.getLogger("apps.admin_panel.views.account_deletion")

PURGE_RETENTION_DAYS = 30
BACKUP_SUBDIR = "account_deletion"


def _now() -> datetime:
    return datetime.now()


def _purge_on(from_dt: datetime | None = None) -> date:
    base = (from_dt or _now()).date()
    return base + timedelta(days=PURGE_RETENTION_DAYS)


def _field(obj, name, default=""):
    """Safe read: Agent has no pan/arn/euin — those live on AgentProfile."""
    if obj is None:
        return default
    try:
        val = getattr(obj, name, default)
    except Exception:
        return default
    return default if val is None else val


def _account_snapshot(agent, reason: str, comments: str) -> dict:
    try:
        profile = agent.profile if agent else None
    except Exception:
        profile = None

    pan = (_field(profile, "pan_number") or "").strip().upper()
    arn = (_field(profile, "arn_number") or "").strip()
    euin = (_field(profile, "euin_number") or "").strip()
    address = (_field(profile, "address") or "").strip()
    state = (_field(profile, "state") or "").strip()
    dob = _field(profile, "date_of_birth", None)
    license_no = (_field(profile, "license_number") or "").strip()

    return {
        "fullname": (_field(agent, "fullname") or "").strip(),
        "email": (_field(agent, "email") or "").strip(),
        "mobile": (_field(agent, "mobile") or "").strip(),
        "pan_number": pan,
        "arn_number": arn,
        "euin_number": euin,
        "profession": (_field(agent, "profession") or "").strip(),
        "pincode": (_field(agent, "agent_pincode") or "").strip(),
        "state": state,
        "city": address[:180],
        "address": address,
        "office_address": (_field(profile, "office_address") or "").strip(),
        "date_of_birth": str(dob or ""),
        "license_number": license_no,
        "agent_status": _field(agent, "status") or "",
        "reason_category": reason or "Account deletion requested",
        "reason_details": comments or "",
        "verification": "password",
    }


def _apply_lock(agent, del_req, notes_line: str, admin_label: str, set_purge: bool):
    """Soft-lock agent, hide profile, suspend login, revoke sessions/tokens."""
    from apps.agents.services.account_auth import end_agent_logins

    now = _now()
    if agent:
        profile = getattr(agent, "profile", None)
        summary = dict(del_req.data_retention_summary or {})
        summary.setdefault("previous_agent_status", agent.status)
        if profile:
            summary.setdefault(
                "previous_profile_visible", bool(profile.is_profile_visible)
            )
            summary.setdefault(
                "previous_card_visible", bool(profile.is_card_visible)
            )
        del_req.data_retention_summary = summary

        try:
            with transaction.atomic():
                profile = getattr(agent, "profile", None)
                if profile:
                    profile.is_profile_visible = False
                    profile.is_card_visible = False
                    profile.save(
                        update_fields=["is_profile_visible", "is_card_visible"]
                    )
        except Exception as e:
            logger.warning("Error updating visibility for agent %s: %s", agent.id, e)

        agent.status = "deleted"
        agent.save(update_fields=["status"])

        if agent.email:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET status = 'suspended' WHERE LOWER(email) = LOWER(%s)",
                    [agent.email],
                )

        if agent.user:
            agent.user.is_active = False
            agent.user.save(update_fields=["is_active"])

        try:
            end_agent_logins(agent)
        except Exception:
            logger.exception("Could not end logins for agent %s", agent.id)

    del_req.status = "COMPLETED"
    del_req.processed_at = now
    del_req.processed_by_admin_name = admin_label
    if set_purge and not del_req.scheduled_purge_date:
        del_req.scheduled_purge_date = _purge_on(now)
    del_req.admin_notes = f"{del_req.admin_notes or ''}\n{notes_line}".strip()
    del_req.save()
    return agent


def terminate_account(del_req, admin_id, admin_notes, log_action):
    """Admin terminate. Returns agent."""
    agent = del_req.agent or Agent.objects.filter(email__iexact=del_req.email).first()
    with transaction.atomic():
        _apply_lock(
            agent,
            del_req,
            notes_line=f"[Admin Termination]: {admin_notes}",
            admin_label=f"Admin #{admin_id}",
            set_purge=True,
        )
        log_action(agent, del_req)
    return agent


def activate_account(del_req, admin_id, admin_notes, log_action):
    """Admin reactivate; cancels scheduled purge. Returns agent."""
    agent = del_req.agent or Agent.objects.filter(email__iexact=del_req.email).first()
    now = _now()
    summary = dict(del_req.data_retention_summary or {})

    with transaction.atomic():
        if agent:
            try:
                with transaction.atomic():
                    profile = getattr(agent, "profile", None)
                    if profile:
                        profile.is_profile_visible = summary.get(
                            "previous_profile_visible", True
                        )
                        profile.is_card_visible = summary.get(
                            "previous_card_visible", True
                        )
                        profile.save(
                            update_fields=["is_profile_visible", "is_card_visible"]
                        )
            except Exception as e:
                logger.warning(
                    "Error restoring visibility for agent %s: %s", agent.id, e
                )

            agent.status = summary.get("previous_agent_status") or "active"
            agent.save(update_fields=["status"])

            if agent.email:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET status = 'active' WHERE LOWER(email) = LOWER(%s)",
                        [agent.email],
                    )

            if agent.user:
                agent.user.is_active = True
                agent.user.save(update_fields=["is_active"])

        cleaned = {
            k: v
            for k, v in summary.items()
            if not k.startswith("previous_")
        }
        cleaned["purge_cancelled_at"] = now.isoformat(timespec="seconds")
        del_req.data_retention_summary = cleaned
        del_req.scheduled_purge_date = None
        del_req.status = "PENDING"
        del_req.processed_at = now
        del_req.processed_by_admin_name = f"Admin #{admin_id}"
        del_req.admin_notes = (
            f"{del_req.admin_notes or ''}\n[Admin Reactivated]: {admin_notes}"
        ).strip()
        del_req.save()
        log_action(agent, del_req)

    return agent


def reject_request(del_req, admin_id, rejection_reason):
    """Kept for legacy rows; new user flow does not use reject."""
    del_req.status = "REJECTED"
    del_req.rejection_reason = rejection_reason
    del_req.processed_at = _now()
    del_req.processed_by_admin_name = f"Admin #{admin_id}"
    del_req.scheduled_purge_date = None
    del_req.save()


def lock_account_for_user_deletion(
    agent,
    *,
    reason: str = "",
    comments: str = "",
    ip_address: str | None = None,
    user_agent: str = "",
):
    """
    Password already verified. Lock immediately, create COMPLETED deletion row,
    schedule purge in 30 days, send confirmation email.

    Returns (del_req, created: bool).
    """
    if not agent:
        raise ValueError("agent is required")

    email_clean = (agent.email or "").strip().lower()
    existing = (
        AccountDeletionRequest.objects.filter(
            agent_id=agent.id,
            status="COMPLETED",
            is_verified=True,
        )
        .order_by("-id")
        .first()
    )
    if existing:
        summary = dict(existing.data_retention_summary or {})
        if not summary.get("purged_at"):
            return existing, False

    reason_clean = (reason or "Account deletion requested").strip()
    comments_clean = (comments or "").strip()
    now = _now()
    ref_id = f"DEL-{now.strftime('%Y%m%d')}-{secrets.token_hex(8).upper()}"
    snapshot = _account_snapshot(agent, reason_clean, comments_clean)

    with transaction.atomic():
        del_req = AccountDeletionRequest(
            reference_id=ref_id,
            identifier=snapshot["pan_number"] or email_clean,
            email=email_clean,
            mobile=agent.mobile or "",
            account_type="agent",
            status="COMPLETED",
            verification_method="password",
            is_verified=True,
            reason=f"[{reason_clean}] {comments_clean}".strip(),
            data_retention_summary=snapshot,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500],
            agent=agent,
            user_id=getattr(agent, "user_id", None),
            scheduled_purge_date=_purge_on(now),
            admin_notes=(
                "Password confirmed by account holder. "
                "Account locked immediately. Private data purge scheduled."
            ),
            processed_at=now,
            processed_by_admin_name="User self-service",
        )
        del_req.save()
        _apply_lock(
            agent,
            del_req,
            notes_line="[User self-delete] Account locked; purge scheduled.",
            admin_label="User self-service",
            set_purge=True,
        )

    try:
        send_deletion_locked_email(agent, del_req)
    except Exception:
        logger.exception(
            "Deletion confirmation email failed for %s (ref %s)",
            email_clean,
            del_req.reference_id,
        )

    return del_req, True


def send_deletion_locked_email(agent, del_req) -> bool:
    from apps.agents.services.brevo import email_service

    to_email = (del_req.email or getattr(agent, "email", "") or "").strip()
    if not to_email:
        return False
    name = (getattr(agent, "fullname", None) or to_email).strip()
    purge = del_req.scheduled_purge_date
    purge_str = purge.strftime("%d %b %Y") if purge else "30 days from request"
    subject = "Your Padosi Agent account has been locked for deletion"
    html = f"""
    <div style="font-family:Arial,sans-serif;line-height:1.6;color:#1a1a2e;">
      <h2 style="color:#135E3E;">Account deletion confirmed</h2>
      <p>Hello {name},</p>
      <p>Your Padosi Agent account has been <strong>locked immediately</strong>
         after your password was verified.</p>
      <ul>
        <li>Reference ID: <strong>{del_req.reference_id}</strong></li>
        <li>Login and public profile are disabled now</li>
        <li>All personal data will be permanently deleted after
            <strong>{purge_str}</strong> (about 1 month)</li>
      </ul>
      <p>If this was a mistake, contact
         <a href="mailto:support@padosiagent.com">support@padosiagent.com</a>
         as soon as possible.</p>
      <p>— Padosi Agent App</p>
    </div>
    """
    return email_service.send_generic(to_email, name, subject, html)


def _backup_dir() -> Path:
    root = Path(getattr(settings, "BASE_DIR", Path("."))) / "backups" / BACKUP_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


def _build_full_backup_payload(agent, del_req) -> dict:
    profile = getattr(agent, "profile", None) if agent else None
    profile_data = {}
    if profile:
        for field in profile._meta.fields:
            name = field.name
            if name in ("id", "agent"):
                continue
            val = getattr(profile, name, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif hasattr(val, "name") and not isinstance(val, str):
                val = str(val.name or "")
            profile_data[name] = val

    agent_data = {}
    if agent:
        for field in agent._meta.fields:
            name = field.name
            if name in ("id", "user", "password"):
                continue
            val = getattr(agent, name, None)
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif hasattr(val, "name") and not isinstance(val, (str, type(None))):
                try:
                    val = str(val.name or "")
                except Exception:
                    val = str(val)
            agent_data[name] = val

    return {
        "reference_id": del_req.reference_id,
        "backed_up_at": _now().isoformat(timespec="seconds"),
        "deletion_request": {
            "id": del_req.id,
            "email": del_req.email,
            "mobile": del_req.mobile,
            "status": del_req.status,
            "reason": del_req.reason,
            "scheduled_purge_date": str(del_req.scheduled_purge_date or ""),
            "data_retention_summary": del_req.data_retention_summary,
        },
        "agent": agent_data,
        "profile": profile_data,
    }


def _write_backup(agent, del_req) -> str:
    payload = _build_full_backup_payload(agent, del_req)
    path = _backup_dir() / f"{del_req.reference_id}.json.gz"
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(raw)
    return str(path)


def _purge_private_fields(agent):
    """Clear PAN/AMFI/KYC/etc on AgentProfile. Keep agent name, phone, email."""
    if not agent:
        return

    try:
        profile = agent.profile
    except Exception:
        profile = None
    if not profile:
        return

    clear_profile = {
        "pan_number": "",
        "arn_number": "",
        "euin_number": "",
        "license_number": "",
        "date_of_birth": None,
        "address": None,
        "office_address": None,
        "state": None,
        "profile_photo_path": None,
        "custom_banner_path": None,
        "agency_logo_path": None,
        "whatsapp": None,
        "gbp_access_token": None,
        "gbp_refresh_token": None,
        "gbp_token_expires_at": None,
        "irdai_license_doc": None,
        "amfi_license_doc": None,
        "social_links": None,
        "career_highlights": None,
        "website_url": None,
        "is_profile_visible": False,
        "is_card_visible": False,
    }
    update_fields = []
    for key, val in clear_profile.items():
        if hasattr(profile, key):
            setattr(profile, key, val)
            update_fields.append(key)
    if update_fields:
        profile.save(update_fields=update_fields)


def purge_due_deletion_requests(limit: int = 50) -> dict:
    """
    Daily job: for COMPLETED requests past scheduled_purge_date,
    write full backup then purge private live fields. Keep name/phone/email.
    """
    today = date.today()
    qs = AccountDeletionRequest.objects.filter(
        status="COMPLETED",
        scheduled_purge_date__lte=today,
        is_verified=True,
    ).order_by("scheduled_purge_date", "id")[:limit]
    stats = {"scanned": 0, "purged": 0, "errors": 0}
    for del_req in qs:
        stats["scanned"] += 1
        summary = dict(del_req.data_retention_summary or {})
        if summary.get("purged_at"):
            continue
        try:
            with transaction.atomic():
                agent = (
                    del_req.agent
                    or Agent.objects.filter(email__iexact=del_req.email).first()
                )
                backup_path = _write_backup(agent, del_req)
                _purge_private_fields(agent)
                summary["purged_at"] = _now().isoformat(timespec="seconds")
                summary["backup_path"] = backup_path
                del_req.data_retention_summary = summary
                del_req.status = "PURGED"
                del_req.admin_notes = (
                    f"{del_req.admin_notes or ''}\n"
                    f"[Auto purge] Private data purged; full backup at {backup_path}"
                ).strip()
                del_req.processed_at = _now()
                del_req.save(
                    update_fields=[
                        "data_retention_summary",
                        "status",
                        "admin_notes",
                        "processed_at",
                        "updated_at",
                    ]
                )
            stats["purged"] += 1
            logger.info(
                "Purged deletion request %s (backup %s)",
                del_req.reference_id,
                backup_path,
            )
        except Exception:
            stats["errors"] += 1
            logger.exception(
                "Failed to purge deletion request %s", del_req.reference_id
            )
    return stats
