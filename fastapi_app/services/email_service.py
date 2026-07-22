import json
import base64
import urllib.request
import urllib.error
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import asyncio
import logging
from typing import Optional, List, Dict, Any
from app.config import settings

logger = logging.getLogger("email_service")

class EmailService:
    @staticmethod
    def send_welcome_email(
        to_email: str, 
        to_name: str, 
        password: str, 
        pdf_content: Optional[bytes] = None, 
        invoice_number: Optional[str] = None
    ) -> bool:
        """
        Sends the welcome email containing username (email) and default password,
        with the generated invoice PDF attached (if provided).
        """
        import os
        from jinja2 import Environment, FileSystemLoader
        from datetime import datetime
        from app.database import SessionLocal
        from sqlalchemy import text

        # Retrieve site logo from database site_settings if available
        logo_url = None
        try:
            db = SessionLocal()
            try:
                row = db.execute(text("SELECT `value` FROM site_settings WHERE `key` = 'site_logo'")).fetchone()
                if row and row[0]:
                    logo_url = row[0]
            finally:
                db.close()
        except Exception:
            pass

        if not logo_url:
            logo_url = f"{settings.APP_URL}/static/img/logo.png"
        elif not (logo_url.startswith("http://") or logo_url.startswith("https://")):
            logo_url = f"{settings.APP_URL}/{logo_url.lstrip('/')}"

        login_url = f"{settings.APP_URL}/agent-login"
        current_year = datetime.utcnow().year

        # Render JINJA welcome email template
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        template_dir = os.path.join(base_dir, "templates")
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template("agent_credentials.html")

        html_content = template.render(
            agent_name=to_name,
            agent_email=to_email,
            password=password,
            logo_url=logo_url,
            login_url=login_url,
            current_year=current_year
        )

        url = "https://api.brevo.com/v3/smtp/email"
        
        payload = {
            "sender": {
                "name": settings.BREVO_FROM_NAME,
                "email": settings.BREVO_FROM_EMAIL
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name
                }
            ],
            "subject": "Welcome to PadosiAgent - Your Account Credentials & Invoice",
            "htmlContent": html_content
        }
        
        if pdf_content and invoice_number:
            pdf_base64 = base64.b64encode(pdf_content).decode("utf-8")
            payload["attachment"] = [
                {
                    "name": f"{invoice_number}.pdf",
                    "content": pdf_base64
                }
            ]
            
        headers = {
            "api-key": settings.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode("utf-8")
                print("Brevo Email Sent:", res_body)
                return True
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"Brevo HTTP Error ({e.code}): {error_body}")
            # If fallback enabled, we return success so that the user doesn't get blocked
            return settings.BREVO_OTP_FALLBACK
        except Exception as ex:
            print(f"Brevo HTTP Connection Error: {ex}")
            return settings.BREVO_OTP_FALLBACK

    @staticmethod
    def _send_brevo_http_sync(
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None
    ) -> bool:
        url = "https://api.brevo.com/v3/smtp/email"
        payload = {
            "sender": {
                "name": settings.BREVO_FROM_NAME or "PadosiAgent",
                "email": settings.BREVO_FROM_EMAIL or "noreply@padosiagent.com"
            },
            "to": [
                {
                    "email": to_email,
                    "name": to_name or to_email
                }
            ],
            "subject": subject,
            "htmlContent": html_content
        }
        headers = {
            "api-key": settings.BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as response:
                response.read()
                return True
        except Exception as e:
            print(f"Brevo HTTP error: {e}")
            return False

    @staticmethod
    def _send_smtp_sync(
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        
        from_name = settings.MAIL_FROM_NAME or "PadosiAgent"
        from_addr = settings.MAIL_FROM_ADDRESS
        msg["From"] = f"{from_name} <{from_addr}>"
        
        to_display = f"{to_name} <{to_email}>" if to_name else to_email
        msg["To"] = to_display

        msg.attach(MIMEText(html_content, "html"))

        encryption = (settings.MAIL_ENCRYPTION or "tls").lower()
        if encryption == "ssl":
            server = smtplib.SMTP_SSL(settings.MAIL_HOST, settings.MAIL_PORT, timeout=15)
        else:
            server = smtplib.SMTP(settings.MAIL_HOST, settings.MAIL_PORT, timeout=15)
            if encryption == "tls":
                server.starttls()

        if settings.MAIL_USERNAME and settings.MAIL_PASSWORD:
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)

        server.sendmail(from_addr, to_email, msg.as_string())
        server.quit()

    @staticmethod
    async def send_smtp_email(
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends an HTML email asynchronously using SMTP.
        Falls back to Brevo HTTP API if SMTP is not configured.
        """
        smtp_configured = all([
            settings.MAIL_HOST,
            settings.MAIL_PORT,
            settings.MAIL_USERNAME,
            settings.MAIL_PASSWORD,
            settings.MAIL_FROM_ADDRESS
        ])

        if smtp_configured:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    EmailService._send_smtp_sync,
                    to_email,
                    subject,
                    html_content,
                    to_name
                )
                return {"success": True, "message": "Email sent successfully via SMTP."}
            except smtplib.SMTPAuthenticationError as auth_err:
                err_msg = f"SMTP Authentication failed: {str(auth_err)}"
                logger.exception(err_msg)
                if not settings.BREVO_API_KEY:
                    return {"success": False, "message": err_msg}
            except smtplib.SMTPConnectError as conn_err:
                err_msg = f"SMTP Connection failed: {str(conn_err)}"
                logger.exception(err_msg)
                if not settings.BREVO_API_KEY:
                    return {"success": False, "message": err_msg}
            except Exception as e:
                err_msg = f"Failed to send SMTP email: {str(e)}"
                logger.exception(err_msg)
                if not settings.BREVO_API_KEY:
                    return {"success": False, "message": err_msg}

        # Fallback to Brevo HTTP API
        if settings.BREVO_API_KEY:
            try:
                loop = asyncio.get_running_loop()
                success = await loop.run_in_executor(
                    None,
                    EmailService._send_brevo_http_sync,
                    to_email,
                    subject,
                    html_content,
                    to_name
                )
                if success:
                    return {"success": True, "message": "Email sent successfully via Brevo HTTP API."}
                else:
                    return {"success": False, "message": "Failed to send email via Brevo HTTP API."}
            except Exception as e:
                return {"success": False, "message": f"Failed to send HTTP email: {str(e)}"}

        return {"success": False, "message": "No email configuration found (SMTP and Brevo HTTP are both unconfigured)."}

    @staticmethod
    async def send_password_reset_email(
        to_email: str,
        to_name: str,
        reset_url: str,
        expiry_minutes: int = 60,
        role_name: str = "Agent"
    ) -> bool:
        """
        Sends a branded password reset email.
        """
        import os
        import base64
        import mimetypes

        logo_src = "https://padosiagents.com/img/logo.png"
        try:
            # Look for logo in public/img/logo.png relative to the workspace root
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # base_dir is app, parent is padosiagent-fastapi, parent of that is django, parent of that is workspace root
            logo_path = os.path.abspath(os.path.join(base_dir, "..", "..", "..", "public", "img", "logo.png"))
            if os.path.exists(logo_path):
                with open(logo_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                    mime_type, _ = mimetypes.guess_type(logo_path)
                    if not mime_type:
                        mime_type = "image/png"
                    logo_src = f"data:{mime_type};base64,{encoded_string}"
        except Exception:
            pass

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password</title>
</head>
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f9;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#273C8E,#1a2a63);padding:28px 40px;text-align:center;">
            <img src="{logo_src}"
                 alt="PadosiAgent"
                 width="180"
                 style="max-width:180px;height:auto;display:block;margin:0 auto;"
            />
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 30px;">
            <h2 style="color:#1a2a63;font-size:20px;margin:0 0 16px;">Hello {to_name}!</h2>
            <p style="color:#4b5563;font-size:15px;line-height:1.7;margin:0 0 16px;">
              We received a request to reset the password for your <strong>{role_name}</strong> account on PadosiAgent.
            </p>
            <p style="color:#4b5563;font-size:15px;line-height:1.7;margin:0 0 30px;">
              Click the button below to reset your password. This link will expire in <strong>{expiry_minutes} minutes</strong>.
            </p>

            <!-- CTA Button -->
            <table cellpadding="0" cellspacing="0" width="100%">
              <tr>
                <td align="center" style="padding:0 0 30px;">
                  <a href="{reset_url}"
                     style="display:inline-block;background:linear-gradient(135deg,#273C8E,#1a2a63);color:#ffffff;text-decoration:none;padding:14px 36px;border-radius:8px;font-size:16px;font-weight:600;letter-spacing:0.3px;">
                    Reset My Password
                  </a>
                </td>
              </tr>
            </table>

            <p style="color:#6b7280;font-size:13px;line-height:1.6;margin:0 0 16px;">
              If the button doesn't work, copy and paste this link into your browser:
            </p>
            <p style="background:#f3f4f6;border-radius:6px;padding:12px 16px;word-break:break-all;font-size:12px;color:#374151;margin:0 0 24px;">
              {reset_url}
            </p>

            <hr style="border:none;border-top:1px solid #e5e7eb;margin:0 0 24px;">

            <p style="color:#9ca3af;font-size:13px;line-height:1.6;margin:0;">
              If you did not request a password reset, no action is needed — your account is safe.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;padding:20px 40px;text-align:center;border-top:1px solid #e5e7eb;">
            <p style="color:#9ca3af;font-size:12px;margin:0;">— The PadosiAgent Team &nbsp;|&nbsp; <a href="https://padosiagents.com" style="color:#273C8E;text-decoration:none;">padosiagents.com</a></p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>
"""
        subject = "PadosiAgent – Reset Your Password"
        res = await EmailService.send_smtp_email(to_email, subject, html_content, to_name)
        return res.get("success", False)
