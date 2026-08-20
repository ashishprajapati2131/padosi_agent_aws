import re
import json
import urllib.request
import urllib.error
import html
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta

from fastapi_app.config import settings
from fastapi_app.database import SessionLocal
from fastapi_app.models.blocked_ip import BlockedIp
from fastapi_app.models.security_threat_log import SecurityThreatLog
from fastapi_app.models.user import User
from fastapi_app.models.agent import Agent

class ThreatMonitorMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Resolve client IP, considering reverse proxies
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "127.0.0.1"

        # 2. Whitelist local/trusted IPs
        if ip in ["127.0.0.1", "::1"]:
            return await call_next(request)

        db = SessionLocal()
        try:
            # 3. Check if IP is blocked in database
            is_blocked = db.query(BlockedIp).filter(BlockedIp.ip_address == ip).first()
            if is_blocked:
                return JSONResponse(
                    status_code=403,
                    content={"error": "Forbidden", "message": "Your IP address has been blocked due to suspicious activity."}
                )

            # 4. Extract input payload and full request URL (avoid reading multipart/form-data request bodies)
            content_type = request.headers.get("content-type", "")
            is_multipart = "multipart/form-data" in content_type

            if is_multipart:
                input_str = ""
            else:
                body_bytes = await request.body()
                
                async def receive():
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                
                request._receive = receive
                input_str = body_bytes.decode("utf-8", errors="ignore")

            url_str = str(request.url)

            # WAF Regex Patterns matching PHP Laravel exactly
            patterns = {
                "SQL Injection": r"(union select\s|select\s+\*\s+from|insert\s+into|update\s+\w+\s+set|'\s*or\s*'1'\s*=\s*'1|sleep\(\d+\)|benchmark\s*\(|group_concat|information_schema)",
                "Cross Site Scripting (XSS)": r"(<script\b[^>]*>|javascript:|onerror=|onload=|eval\(|setTimeout\(|setInterval\(|alert\(|document\.cookie|document\.domain|window\.location)",
                "Path Traversal / LFI": r"(\.\.\/|\.\.\\\\|\/etc\/passwd|\/etc\/shadow|\/etc\/group|\/etc\/hosts|\/proc\/self|php:\/\/filter|php:\/\/input|expect:\/\/)",
                "RCE / Shell Injection": r"(system\(|exec\(|passthru\(|shell_exec\(|proc_open\(|pcntl_exec\(|python\s+-c|perl\s+-e|ruby\s+-e|bash\s+-i|nc\s+-e)",
                "SSRF / Metadata API": r"(169\.254\.169\.254|metadata\.google\.internal|\/latest\/meta-data\/)",
                "XML External Entity (XXE)": r"(<!ENTITY\s+|SYSTEM\s+[\"']|PUBLIC\s+[\"'])",
                "Server-Side Template Injection": r"({{\s*[\s\S]*\s*}}|{%\s*[\s\S]*\s*%}|\[\[\s*[\s\S]*\s*\]\])",
                "CRLF / Header Injection": r"(\%0d\%0a|\r\n|Set-Cookie:|Content-Type:)",
            }

            type_matched = None
            for type_name, pattern in patterns.items():
                if re.search(pattern, input_str, re.IGNORECASE) or re.search(pattern, url_str, re.IGNORECASE):
                    type_matched = type_name
                    break

            if type_matched:
                # 6. Malicious Activity Detected - Gather Hacker details
                hacker_name = "GUEST / ANONYMOUS"
                hacker_email = None
                hacker_mobile = None

                auth_header = request.headers.get("authorization")
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    try:
                        from fastapi_app.utils.auth import decode_token
                        payload = decode_token(token)
                        if payload and payload.get("sub"):
                            email = payload.get("sub")
                            user = db.query(User).filter(User.email == email).first()
                            if user:
                                hacker_name = user.fullname
                                hacker_email = user.email
                                agent = db.query(Agent).filter(Agent.email == email).first()
                                if agent:
                                    hacker_mobile = agent.mobile
                    except Exception:
                        pass

                # 7. Query Location & ISP
                location = "N/A"
                isp = "N/A"
                try:
                    req_geo = urllib.request.Request(
                        f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,isp",
                        headers={"User-Agent": "Mozilla/5.0 (Security Grid)"},
                        timeout=2.0
                    )
                    with urllib.request.urlopen(req_geo) as resp_geo:
                        geo_data = json.loads(resp_geo.read().decode("utf-8"))
                        if geo_data.get("status") == "success":
                            location = f"{geo_data.get('city')}, {geo_data.get('regionName')}, {geo_data.get('country')}"
                            isp = geo_data.get("isp")
                except Exception:
                    try:
                        req_geo2 = urllib.request.Request(
                            f"https://ipwho.is/{ip}",
                            headers={"User-Agent": "Mozilla/5.0 (Security Grid)"},
                            timeout=2.0
                        )
                        with urllib.request.urlopen(req_geo2) as resp_geo2:
                            geo_data2 = json.loads(resp_geo2.read().decode("utf-8"))
                            if geo_data2.get("success"):
                                location = f"{geo_data2.get('city')}, {geo_data2.get('region')}, {geo_data2.get('country')}"
                                isp = geo_data2.get("connection", {}).get("isp", "N/A")
                    except Exception:
                        pass

                # 8. Check auto-ban threshold (3 threats within 1 hour)
                is_auto_blocked = False
                ban_reason = ""
                if settings.WAF_AUTO_BAN_ENABLED:
                    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
                    recent_threats_count = db.query(SecurityThreatLog).filter(
                        SecurityThreatLog.ip_address == ip,
                        SecurityThreatLog.created_at >= one_hour_ago
                    ).count()
                    
                    if recent_threats_count >= 2:  # this would be the 3rd offense
                        # Ban IP
                        already_blocked = db.query(BlockedIp).filter(BlockedIp.ip_address == ip).first()
                        if not already_blocked:
                            blocked_ip = BlockedIp(
                                ip_address=ip,
                                reason=f"Auto-blocked by Threat Monitor due to recurring malicious payloads ({type_matched})."
                            )
                            db.add(blocked_ip)
                        is_auto_blocked = True
                        ban_reason = "Auto-blocked due to 3+ malicious payload detections in 1 hour."

                # 9. Record Threat Log in database
                threat_log = SecurityThreatLog(
                    ip_address=ip,
                    event_type=type_matched,
                    hacker_name=hacker_name,
                    hacker_email=hacker_email,
                    hacker_mobile=hacker_mobile,
                    location=location,
                    isp=isp,
                    url=url_str,
                    payload=input_str[:1000],
                    user_agent=request.headers.get("user-agent", "N/A")
                )
                db.add(threat_log)
                db.commit()

                # 10. Send Brevo SMTP Security Alert Email to ashisprajapati2131@gmail.com
                try:
                    threat_html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                        <h2 style="color: #c0392b;">⚠️ SECURITY ALERT: Malicious Activity Detected on PadosiAgent</h2>
                        <p>A security threat event was detected and blocked by the FastAPI Threat Monitor WAF.</p>
                        <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%; max-width: 600px; border-color: #ddd;">
                            <tr bgcolor="#f2f2f2"><th align="left">Field</th><th align="left">Details</th></tr>
                            <tr><td><strong>IP Address</strong></td><td>{ip}</td></tr>
                            <tr><td><strong>Event Type</strong></td><td>{type_matched}</td></tr>
                            <tr><td><strong>Request URL</strong></td><td>{url_str}</td></tr>
                            <tr><td><strong>Location</strong></td><td>{location}</td></tr>
                            <tr><td><strong>ISP</strong></td><td>{isp}</td></tr>
                            <tr><td><strong>Hacker Account</strong></td><td>{hacker_name} ({hacker_email or 'Guest'})</td></tr>
                            <tr><td><strong>Auto-Banned?</strong></td><td>{'YES' if is_auto_blocked else 'NO'} {f'({ban_reason})' if is_auto_blocked else ''}</td></tr>
                            <tr><td><strong>User Agent</strong></td><td>{request.headers.get("user-agent", "N/A")}</td></tr>
                        </table>
                        <p><strong>Payload preview (first 500 chars):</strong></p>
                        <pre style="background: #f8f9fa; padding: 10px; border: 1px solid #ddd; max-width: 600px; overflow-x: auto;">{html.escape(input_str[:500])}</pre>
                    </body>
                    </html>
                    """
                    
                    brevo_payload = {
                        "sender": {"name": "Security Grid", "email": settings.BREVO_FROM_EMAIL or "noreply@padosiagent.com"},
                        "to": [{"email": settings.SECURITY_ALERT_EMAIL, "name": "Security Admin"}],
                        "subject": "⚠️ SECURITY ALERT: Malicious Activity Detected on PadosiAgent",
                        "htmlContent": threat_html
                    }
                    
                    req_email = urllib.request.Request(
                        "https://api.brevo.com/v3/smtp/email",
                        data=json.dumps(brevo_payload).encode("utf-8"),
                        headers={
                            "api-key": settings.BREVO_API_KEY,
                            "Content-Type": "application/json",
                            "Accept": "application/json"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req_email) as resp_email:
                        resp_email.read()
                except Exception as email_err:
                    # Non-blocking, keep middleware robust
                    print(f"Failed to send security alert email: {email_err}")

                return JSONResponse(
                    status_code=403,
                    content={"error": "Forbidden", "message": "Malicious activity detected."}
                )

        finally:
            db.close()

        return await call_next(request)
