import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.dependencies.auth import get_current_user
from fastapi_app.models.account_deletion_request import AccountDeletionRequest
from fastapi_app.models.user import User
from fastapi_app.schemas.account_deletion import (
    RequestDeletionByPasswordSchema,
    RequestDeletionPublicSchema,
    DeletionResponseSchema,
    DeletionStatusDetailSchema,
)


logger = logging.getLogger("account_deletion")

router = APIRouter(
    prefix="/v1/account-deletion",
    tags=["Account Deletion"],
)

_GENERIC_PUBLIC_AUTH_ERROR = "Email or password is incorrect."


def _now() -> datetime:
    """Naive local (IST) time, the clock Django uses with USE_TZ=False."""
    return datetime.now()


def _get_client_ip(request: Request) -> str:
    from fastapi_app.utils.client_ip import get_client_ip

    return get_client_ip(request)


def _django_agent_from_jwt_user(current_user: User):
    """Resolve the Django Agent for the login JWT user. Body never picks the account."""
    from apps.agents.models import Agent as DjangoAgent
    from apps.agents.services.account_auth import find_agent

    email = (current_user.email or "").strip()
    agent = find_agent(email) if email else None
    if agent is None and getattr(current_user, "id", None):
        # Same fallback as get_current_agent when email on the token/user drifted.
        candidate = DjangoAgent.objects.filter(user_id=current_user.id).first()
        if candidate and email and (candidate.email or "").lower() == email.lower():
            agent = candidate
        elif candidate and not email:
            agent = candidate
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent profile not found.",
        )
    return agent


def _response_from_del_req(del_req, *, created: bool) -> DeletionResponseSchema:
    purge = del_req.scheduled_purge_date
    purge_on = purge.isoformat() if purge else None
    if created:
        message = (
            "Your account has been locked. Login is disabled. "
            "All personal data will be permanently deleted after 1 month. "
            "A confirmation email has been sent."
        )
    else:
        message = (
            "This account is already locked for deletion. "
            "Personal data will be permanently deleted on the scheduled date."
        )
    return DeletionResponseSchema(
        success=True,
        message=message,
        reference_id=del_req.reference_id,
        status=del_req.status,
        purge_on=purge_on,
    )


def _lock_after_password_ok(agent, payload, request: Request) -> DeletionResponseSchema:
    from apps.admin_panel.services.account_deletion_service import (
        lock_account_for_user_deletion,
    )

    try:
        del_req, created = lock_account_for_user_deletion(
            agent,
            reason=getattr(payload, "reason", None) or "",
            comments=getattr(payload, "comments", None) or "",
            ip_address=_get_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:500],
        )
    except Exception:
        logger.exception("Account deletion lock failed for agent_id=%s", getattr(agent, "id", None))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not complete account deletion. Please try again.",
        )
    return _response_from_del_req(del_req, created=created)


@router.delete("/request", response_model=DeletionResponseSchema)
def request_deletion_with_password(
    payload: RequestDeletionByPasswordSchema,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    App delete: Authorization Bearer = login JWT (same token from login).

    JWT identifies which account; password in the body confirms the holder.
    Does not use get_current_agent so expired subscription still allows delete.
    """
    agent = _django_agent_from_jwt_user(current_user)
    from apps.agents.services.account_auth import verify_agent_password

    try:
        password_ok, _, _ = verify_agent_password(agent.email, payload.password, agent=agent)
    except Exception:
        logger.exception("Account deletion password check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not check the password. Please try again.",
        )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is incorrect.",
        )

    return _lock_after_password_ok(agent, payload, request)


@router.delete("/request-public", response_model=DeletionResponseSchema)
def request_deletion_public(
    payload: RequestDeletionPublicSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Public web / Play Console: email + password → immediate lock.
    Wrong email or password returns the same generic error.
    """
    from apps.agents.services.account_auth import find_agent, verify_agent_password

    email = (payload.email or "").strip().lower()
    agent = find_agent(email) if email else None
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_PUBLIC_AUTH_ERROR,
        )

    try:
        password_ok, _, _ = verify_agent_password(agent.email, payload.password, agent=agent)
    except Exception:
        logger.exception("Public account deletion password check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not check the password. Please try again.",
        )
    if not password_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_GENERIC_PUBLIC_AUTH_ERROR,
        )

    return _lock_after_password_ok(agent, payload, request)


@router.get("/status/{reference_id}", response_model=DeletionStatusDetailSchema)
def get_deletion_status(
    reference_id: str,
    db: Session = Depends(get_db),
):
    """Public status check; personal fields are masked (audit API1)."""
    del_req = (
        db.query(AccountDeletionRequest)
        .filter(AccountDeletionRequest.reference_id == reference_id.strip())
        .first()
    )

    if not del_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference ID not found. Please verify the ID entered.",
        )

    summary = dict(del_req.data_retention_summary or {})
    sub_at_str = (
        del_req.created_at.strftime("%d %b %Y, %I:%M %p") if del_req.created_at else "-"
    )
    proc_at_str = (
        del_req.processed_at.strftime("%d %b %Y, %I:%M %p")
        if del_req.processed_at
        else "Pending Action"
    )
    purge_date = del_req.scheduled_purge_date
    purge_on = None
    if purge_date is not None and hasattr(purge_date, "isoformat"):
        try:
            purge_on = purge_date.isoformat()
        except Exception:
            purge_on = None

    if del_req.status == "PURGED" or summary.get("purged_at"):
        status_display = "Data purged"
        msg = (
            "Your account was locked and personal data has been permanently deleted "
            f"after the retention period. (Verified: {del_req.is_verified})"
        )
    elif del_req.status == "COMPLETED":
        status_display = "Account locked"
        msg = (
            "Your account is locked. Login is disabled. "
            "All personal data will be permanently deleted after 1 month "
            f"(scheduled: {purge_on or 'pending'}). "
            f"(Verified: {del_req.is_verified})"
        )
    elif del_req.status == "REJECTED":
        status_display = "Rejected"
        rej_msg = (
            del_req.rejection_reason
            or "Account details mismatch or policy criteria not met."
        )
        msg = f"Your deletion request was rejected. Reason: {rej_msg}"
    else:
        status_display = "Account active again"
        msg = (
            "This account was reactivated by administration. "
            f"(Verified: {del_req.is_verified})"
        )

    return DeletionStatusDetailSchema(
        success=True,
        message=msg,
        reference_id=del_req.reference_id,
        status=del_req.status,
        status_display=status_display,
        is_verified=del_req.is_verified,
        fullname=_mask_name(summary.get("fullname") or del_req.identifier),
        email=_mask_email(del_req.email),
        mobile=_mask_mobile(del_req.mobile),
        submitted_at=sub_at_str,
        processed_at=proc_at_str,
        reason=summary.get("reason_category") or del_req.reason,
        rejection_reason=del_req.rejection_reason or "",
        admin_notes="",
        purge_on=purge_on,
    )


def _mask_email(email):
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    return f"{local[:2]}***@{domain}"


def _mask_mobile(mobile):
    digits = "".join(ch for ch in str(mobile or "") if ch.isdigit())
    return f"******{digits[-4:]}" if len(digits) >= 4 else None


def _mask_name(name):
    parts = str(name or "").split()
    if not parts or "@" in parts[0] or parts[0].isdigit():
        return None
    return " ".join([parts[0]] + [p[0] + "." for p in parts[1:]])
