import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from fastapi_app.database import get_db
from fastapi_app.models.account_deletion_request import AccountDeletionRequest
from fastapi_app.models.agent import Agent
from fastapi_app.models.agent_profile import AgentProfile
from fastapi_app.models.user import User
from fastapi_app.schemas.account_deletion import (
    RequestDeletionOtpSchema,
    VerifyDeletionOtpSchema,
    DeletionResponseSchema,
    DeletionStatusDetailSchema,
)


logger = logging.getLogger("account_deletion")

router = APIRouter(
    prefix="/v1/account-deletion",
    tags=["Account Deletion"],
)


def _hash_otp(otp: str, salt: str = "padosi_del_salt_2026") -> str:
    return hashlib.sha256(f"{salt}_{otp}".encode("utf-8")).hexdigest()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _send_deletion_otp_email(to_email: str, fullname: str, otp: str, reference_id: str) -> bool:
    """Sends OTP verification email for account deletion using Brevo/SMTP."""
    subject = f"Your PadosiAgent Account Deletion Code: {otp}"
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f6f9fc; margin: 0; padding: 20px; color: #333; }}
        .card {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border: 1px solid #eef2f6; }}
        .header {{ background: linear-gradient(135deg, #d90429, #ef233c); color: white; padding: 25px 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }}
        .body {{ padding: 30px; }}
        .otp-box {{ background: #fdf2f2; border: 2px dashed #ef233c; border-radius: 8px; text-align: center; padding: 18px; margin: 25px 0; }}
        .otp-code {{ font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #d90429; font-family: 'Courier New', monospace; }}
        .warning-box {{ background: #fffbe6; border-left: 4px solid #faad14; padding: 12px 16px; margin: 20px 0; border-radius: 4px; font-size: 13px; color: #595959; }}
        .footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #8c8c8c; border-top: 1px solid #f0f0f0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>Account Deletion Verification</h1>
        </div>
        <div class="body">
          <p>Hello <strong>{fullname}</strong>,</p>
          <p>We received a formal request to delete and terminate your <strong>PadosiAgent</strong> account.</p>
          <p>To confirm that you are the verified owner of this account, please use the following one-time verification code:</p>
          
          <div class="otp-box">
            <div style="font-size: 12px; text-transform: uppercase; color: #666; letter-spacing: 1px; margin-bottom: 5px;">Your Verification Code</div>
            <div class="otp-code">{otp}</div>
            <div style="font-size: 12px; color: #888; margin-top: 5px;">Valid for 10 minutes</div>
          </div>

          <div class="warning-box">
            <strong>Important Notice:</strong> Upon verification and subsequent administrative execution, your personal and sensitive data (PAN, addresses, KYC documents, claims stats, and segments) will be permanently destroyed. Your name, phone, and invoice history will be retained solely for legal and regulatory compliance.
          </div>

          <p style="font-size: 13px; color: #666;">
            <strong>Reference ID:</strong> <span style="font-family: monospace;">{reference_id}</span><br>
            If you did not request this deletion, please contact our support team immediately or ignore this email.
          </p>
        </div>
        <div class="footer">
          &copy; {datetime.now().year} PadosiAgent Technologies Pvt Ltd. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    # 1. Try BrevoEmailService from apps.agents.services.brevo
    try:
        from apps.agents.services.brevo import email_service
        sent = email_service.send_generic(to_email, fullname, subject, html_content)
        if sent:
            return True
    except Exception as ex:
        logger.warning(f"Brevo email_service generic send failed: {ex}")

    # 2. Try FastAPI EmailService HTTP Brevo / SMTP
    try:
        from fastapi_app.services.email_service import EmailService
        sent = EmailService._send_brevo_http_sync(to_email, subject, html_content, fullname)
        if sent:
            return True
    except Exception as ex:
        logger.warning(f"FastAPI EmailService brevo failed: {ex}")

    # 3. Always log in local/dev so OTP is testable
    logger.info(f"[DELETION OTP] to={to_email} otp={otp} ref={reference_id}")
    return True


@router.post("/request-otp", response_model=DeletionResponseSchema)
def request_deletion_otp(
    payload: RequestDeletionOtpSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Step 1: Validate agent credentials (Name, Phone, Email, PAN),
    generate a secure 6-digit OTP, send it to registered email,
    and initialize an AccountDeletionRequest record.
    """
    email_clean = payload.email.strip().lower()
    mobile_clean = payload.mobile.strip()
    pan_clean = payload.pan_number.strip().upper()
    name_clean = payload.fullname.strip()

    # 1. Strictly verify that the email exists in the Agent database
    agent = db.query(Agent).filter(func.lower(Agent.email) == email_clean).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The email address entered does not exist in our system. Please provide your registered account email.",
        )

    # 2. Strictly verify that the PAN number matches the Agent's profile on record
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first()
    stored_pan = (profile.pan_number or "").strip().upper() if profile else ""
    if not stored_pan or stored_pan != pan_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The PAN number provided does not match our records for this account.",
        )

    # 3. Verify mobile number matches the registered agent mobile
    if agent.mobile and agent.mobile.strip() != mobile_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The phone number provided does not match our records for this account.",
        )

    agent_id = agent.id
    user_id = agent.user_id


    # Generate 6-digit OTP and Reference ID
    otp_code = str(secrets.randbelow(900000) + 100000)
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=10)
    ref_id = f"DEL-{now.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

    client_ip = _get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:500]

    retention_summary = {
        "fullname": name_clean,
        "pan_number": pan_clean,
        "reason_category": payload.reason,
        "reason_details": payload.comments or "",
        "otp_hash": _hash_otp(otp_code),
        "otp_expires_at": expires_at.isoformat(),
        "otp_attempts": 0,
    }

    # Store in database
    del_req = AccountDeletionRequest(
        reference_id=ref_id,
        identifier=pan_clean,
        email=email_clean,
        mobile=mobile_clean,
        account_type="agent",
        status="PENDING",
        verification_method="otp_email",
        is_verified=False,
        reason=f"[{payload.reason}] {payload.comments or ''}".strip(),
        data_retention_summary=retention_summary,
        ip_address=client_ip,
        user_agent=user_agent,
        agent_id=agent_id,
        user_id=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(del_req)
    db.commit()

    # Dispatch Email
    _send_deletion_otp_email(email_clean, name_clean, otp_code, ref_id)

    return DeletionResponseSchema(
        success=True,
        message=f"A 6-digit verification code has been sent to your registered email ({email_clean}).",
        reference_id=ref_id,
        status="PENDING",
    )


@router.post("/verify-otp", response_model=DeletionResponseSchema)
def verify_deletion_otp(
    payload: VerifyDeletionOtpSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Step 2: Verify the 6-digit OTP, mark the deletion request
    as verified, and forward it to the admin panel for termination.
    """
    ref_id = payload.reference_id.strip()
    email_clean = payload.email.strip().lower()
    otp_input = payload.otp.strip()

    del_req = db.query(AccountDeletionRequest).filter(
        AccountDeletionRequest.reference_id == ref_id,
        AccountDeletionRequest.email == email_clean,
    ).first()

    if not del_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account deletion request not found or invalid reference ID.",
        )

    if del_req.is_verified:
        return DeletionResponseSchema(
            success=True,
            message="Your account deletion request has already been verified and is awaiting administrative processing.",
            reference_id=del_req.reference_id,
            status=del_req.status,
        )

    summary = dict(del_req.data_retention_summary or {})
    attempts = int(summary.get("otp_attempts", 0))

    if attempts >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum verification attempts exceeded. Please submit a new request.",
        )

    expires_str = summary.get("otp_expires_at")
    if expires_str:
        try:
            expires_at = datetime.fromisoformat(expires_str)
            if datetime.utcnow() > expires_at:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Verification code has expired. Please request a new code.",
                )
        except Exception:
            pass

    expected_hash = summary.get("otp_hash")
    input_hash = _hash_otp(otp_input)

    if input_hash != expected_hash:
        summary["otp_attempts"] = attempts + 1
        del_req.data_retention_summary = summary
        db.commit()
        remaining = max(0, 5 - (attempts + 1))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. {remaining} attempt(s) remaining.",
        )

    # Success: Mark as verified and pending administrative action
    now = datetime.utcnow()
    del_req.is_verified = True
    del_req.status = "PENDING"
    del_req.admin_notes = (
        f"OTP verified successfully via email at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}. "
        f"Awaiting administrative termination approval."
    )
    summary["verified_at"] = now.isoformat()
    del_req.data_retention_summary = summary
    del_req.updated_at = now
    db.commit()

    return DeletionResponseSchema(
        success=True,
        message=(
            "Your deletion request has been verified and received by the administration panel. "
            "Our compliance team will review and terminate the account. "
            "As specified, your personal KYC, documents, and stats will be purged while identity records "
            "are preserved for regulatory compliance."
        ),
        reference_id=del_req.reference_id,
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
    del_req = db.query(AccountDeletionRequest).filter(
        AccountDeletionRequest.reference_id == reference_id.strip()
    ).first()

    if not del_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reference ID not found. Please verify the ID entered.",
        )

    summary = dict(del_req.data_retention_summary or {})
    
    # Format submitted_at and processed_at
    sub_at_str = del_req.created_at.strftime('%d %b %Y, %I:%M %p') if del_req.created_at else "-"
    proc_at_str = del_req.processed_at.strftime('%d %b %Y, %I:%M %p') if del_req.processed_at else "Pending Action"

    if del_req.status == "COMPLETED":
        status_display = "Terminated"
        msg = f"Your account has been terminated by administration. Request status is COMPLETED. (Verified: {del_req.is_verified})"
    elif del_req.status == "REJECTED":
        status_display = "Rejected"
        rej_msg = del_req.rejection_reason or "Account details mismatch or policy criteria not met."
        msg = f"Your deletion request was rejected. Reason: {rej_msg}"
    else:
        status_display = "Pending Review" if del_req.is_verified else "Awaiting OTP Verification"
        msg = f"Request status is PENDING. (Verified: {del_req.is_verified})"

    return DeletionStatusDetailSchema(
        success=True,
        message=msg,
        reference_id=del_req.reference_id,
        status=del_req.status,
        status_display=status_display,
        is_verified=del_req.is_verified,
        fullname=summary.get("fullname") or del_req.identifier,
        email=del_req.email,
        mobile=del_req.mobile,
        submitted_at=sub_at_str,
        processed_at=proc_at_str,
        reason=summary.get("reason_category") or del_req.reason,
        rejection_reason=del_req.rejection_reason or "",
        admin_notes=del_req.admin_notes or "",
    )

