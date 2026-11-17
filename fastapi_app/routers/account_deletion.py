import logging
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from fastapi_app.database import get_db
from fastapi_app.models.account_deletion_request import AccountDeletionRequest
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.schemas.account_deletion import (
    RequestDeletionByPasswordSchema,
    DeletionResponseSchema,
    DeletionStatusDetailSchema,
)


logger = logging.getLogger("account_deletion")

router = APIRouter(
    prefix="/v1/account-deletion",
    tags=["Account Deletion"],
)


def _now() -> datetime:
    """Naive local (IST) time, the clock Django uses with USE_TZ=False."""
    return datetime.now()


def _get_client_ip(request: Request) -> str:
    from fastapi_app.utils.client_ip import get_client_ip

    return get_client_ip(request)


def _logged_in_agent(request: Request):
    """The agent behind this call: app bearer token, or the website session cookie.

    Email is never taken from the body, so one login cannot request deletion of another account.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.models import Session

    from apps.agents.services.account_auth import find_agent, resolve_agent_for_user
    from fastapi_app.utils.auth import decode_access_token

    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please log in again.",
            )
        email = (payload.get("sub") or "").strip()
        if not email or payload.get("role") != "agent":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please log in again.",
            )
        agent = find_agent(email)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Please log in again.",
            )
        return agent

    session_key = request.cookies.get("sessionid")
    if not session_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to delete your account.",
        )
    try:
        session = Session.objects.filter(session_key=session_key).first()
        data = session.get_decoded() if session else {}
    except Exception:
        data = {}
    user_id = data.get("_auth_user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to delete your account.",
        )
    user = get_user_model().objects.filter(pk=user_id).first()
    agent = resolve_agent_for_user(user) if user else None
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in with the agent account you want to delete.",
        )
    return agent


def _account_snapshot(agent, profile, reason: str, comments: str) -> dict:
    """Identity the admin reviews. The account itself is not removed."""
    return {
        "fullname": (agent.fullname or "").strip(),
        "email": (agent.email or "").strip(),
        "mobile": (agent.mobile or "").strip(),
        "pan_number": ((profile.pan_number if profile else "") or "").strip().upper(),
        "profession": (agent.profession or "").strip(),
        "pincode": (agent.agent_pincode or "").strip(),
        "state": ((profile.state if profile else "") or "").strip(),
        "city": ((getattr(profile, "address", None) or "") if profile else "").strip()[:180],
        "agent_status": agent.status or "",
        "reason_category": reason or "Account deletion requested",
        "reason_details": comments or "",
        "verification": "password",
    }


@router.post("/request", response_model=DeletionResponseSchema)
def request_deletion_with_password(
    payload: RequestDeletionByPasswordSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Logged-in agent confirms their password. A match files a request for an admin.

    A wrong password is rejected and nothing is saved. The agent row is never
    deleted here. An admin approves it from /admin/account-deletion-requests/.
    """
    agent = _logged_in_agent(request)
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

    email_clean = (agent.email or "").strip().lower()
    existing = (
        db.query(AccountDeletionRequest)
        .filter(
            AccountDeletionRequest.agent_id == agent.id,
            AccountDeletionRequest.status == "PENDING",
            AccountDeletionRequest.is_verified.is_(True),
        )
        .order_by(AccountDeletionRequest.id.desc())
        .first()
    )
    if existing:
        return DeletionResponseSchema(
            success=True,
            message=(
                "A deletion request for this account is already waiting for an admin. "
                "The account stays active until that request is approved."
            ),
            reference_id=existing.reference_id,
            status="PENDING",
        )

    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first()
    reason = (payload.reason or "Account deletion requested").strip()
    comments = (payload.comments or "").strip()
    now = _now()
    ref_id = f"DEL-{now.strftime('%Y%m%d')}-{secrets.token_hex(8).upper()}"
    summary = _account_snapshot(agent, profile, reason, comments)

    del_req = AccountDeletionRequest(
        reference_id=ref_id,
        identifier=summary["pan_number"] or email_clean,
        email=email_clean,
        mobile=agent.mobile or "",
        account_type="agent",
        status="PENDING",
        verification_method="password",
        is_verified=True,
        reason=f"[{reason}] {comments}".strip(),
        data_retention_summary=summary,
        ip_address=_get_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:500],
        agent_id=agent.id,
        user_id=getattr(agent, "user_id", None),
        admin_notes="Password confirmed by the logged-in account holder. Waiting for admin approval. Account not deleted.",
        created_at=now,
        updated_at=now,
    )
    db.add(del_req)
    db.commit()

    return DeletionResponseSchema(
        success=True,
        message=(
            "Your deletion request was sent to the admin team. "
            "Your account is still active. It is closed only after an admin approves the request. "
            "Name, phone, email, and compliance records are kept."
        ),
        reference_id=ref_id,
        status="PENDING",
    )


@router.get("/status/{reference_id}", response_model=DeletionStatusDetailSchema)
def get_deletion_status(
    reference_id: str,
    db: Session = Depends(get_db),
):
    """
    Allows user or admin to check the detailed status of an account deletion request.
    Returns submission time, processed time, rejection reason (if any), and current status.
    """
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

    # Format submitted_at and processed_at
    sub_at_str = (
        del_req.created_at.strftime("%d %b %Y, %I:%M %p") if del_req.created_at else "-"
    )
    proc_at_str = (
        del_req.processed_at.strftime("%d %b %Y, %I:%M %p")
        if del_req.processed_at
        else "Pending Action"
    )

    if del_req.status == "COMPLETED":
        status_display = "Terminated"
        msg = f"Your account has been terminated by administration. Request status is COMPLETED. (Verified: {del_req.is_verified})"
    elif del_req.status == "REJECTED":
        status_display = "Rejected"
        rej_msg = (
            del_req.rejection_reason
            or "Account details mismatch or policy criteria not met."
        )
        msg = f"Your deletion request was rejected. Reason: {rej_msg}"
    else:
        status_display = (
            "Pending admin approval"
        )
        msg = f"Request status is PENDING. (Verified: {del_req.is_verified})"

    return DeletionStatusDetailSchema(
        success=True,
        message=msg,
        reference_id=del_req.reference_id,
        status=del_req.status,
        status_display=status_display,
        is_verified=del_req.is_verified,
        # Anyone holding the ref can call this, so personal data is masked and staff notes stay
        # internal (audit API1).
        fullname=_mask_name(summary.get("fullname") or del_req.identifier),
        email=_mask_email(del_req.email),
        mobile=_mask_mobile(del_req.mobile),
        submitted_at=sub_at_str,
        processed_at=proc_at_str,
        reason=summary.get("reason_category") or del_req.reason,
        rejection_reason=del_req.rejection_reason or "",
        admin_notes="",
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
