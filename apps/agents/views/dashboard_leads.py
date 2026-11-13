"""Lead capture from public agent pages (split out of dashboard.py), including the
background lead e-mail thread wrapper _with_fresh_db."""

from apps.agents.models import (
    Agent,
    AgentDeviceToken,
    AgentLead,
)
from apps.home.models import SiteSetting
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from json import loads as json_loads
from apps.agents.views.dashboard_common import logger


def _with_fresh_db(fn):
    """Run fn in a thread and close its DB connection afterwards (audit AG19: threads leaked
    MySQL connections until the server timed them out)."""

    def run(*args, **kwargs):
        from django.db import close_old_connections

        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return run



@csrf_exempt
@require_POST
def agent_capture_lead(request):
    try:
        agent_id = request.POST.get("agent_id")
        interaction_type = request.POST.get("interaction_type")
        service_type = request.POST.get("service_type")
        insurance_type = request.POST.get("insurance_type")
        insurance_company = request.POST.get("insurance_company")
        source_page = request.POST.get("source_page")

        if not agent_id or not interaction_type:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Missing required fields: agent_id and interaction_type.",
                },
                status=400,
            )

        allowed_types = [
            "call",
            "whatsapp",
            "linkedin",
            "facebook",
            "instagram",
            "youtube",
            "google_business",
        ]
        if interaction_type not in allowed_types:
            return JsonResponse(
                {"success": False, "message": "Invalid interaction type."}, status=400
            )

        # Get client IP (trusted-proxy rule; a raw X-Forwarded-For let callers
        # rotate IPs to bypass the per-IP lead limit below)
        from apps.admin_panel.middleware import ThreatMonitorMiddleware

        client_ip = ThreatMonitorMiddleware.get_client_ip(request)

        # 1. Explicit IP Block Check
        from apps.admin_panel.middleware import is_ip_blocked

        if is_ip_blocked(client_ip):
            return JsonResponse(
                {
                    "success": False,
                    "url": "#",
                    "message": "Access denied. Your IP address has been blocked due to suspicious activity.",
                }
            )

        # Check Agent exists
        agent = Agent.objects.filter(id=agent_id).first()
        from apps.agents.views.qr import _card_viewer_is_privileged, _hidden_from_public

        if not agent or _hidden_from_public(agent):  # audit AG3
            return JsonResponse(
                {"success": False, "message": "Agent not found."}, status=404
            )

        # 2. Dynamic Rate Limiting (Unique Agents per IP)
        allowed_unique_leads = int(SiteSetting.get_value("rate_limit_clicks", 10))
        timeframe_hours = int(SiteSetting.get_value("rate_limit_timeframe", 2))

        time_threshold = timezone.now() - timezone.timedelta(hours=timeframe_hours)

        unique_interactions_count = (
            AgentLead.objects.filter(
                ip_address=client_ip, created_at__gte=time_threshold
            )
            .order_by()
            .values("agent_id")
            .distinct()
            .count()
        )

        if unique_interactions_count >= allowed_unique_leads:
            is_same_interaction_allowed = AgentLead.objects.filter(
                ip_address=client_ip,
                agent_id=agent_id,
                interaction_type=interaction_type,
                created_at__gte=time_threshold,
            ).exists()

            if not is_same_interaction_allowed:
                return JsonResponse(
                    {
                        "success": False,
                        "url": "#",
                        "message": f"Rate limit exceeded: You can only contact {allowed_unique_leads} different agents every {timeframe_hours} hours. Please try again later.",
                    }
                )

        # Resolve customer details
        lead_user = request.session.get("quick_lead_user", {})
        customer_name = lead_user.get("fullname") or request.POST.get("fullname")
        customer_email = lead_user.get("email") or request.POST.get("email")
        customer_mobile = lead_user.get("mobile") or request.POST.get("mobile")
        customer_pincode = lead_user.get("pincode") or request.POST.get("pincode")

        if (
            not customer_name or not customer_email or not customer_mobile
        ) and request.user.is_authenticated:
            user = request.user
            customer_name = (
                customer_name
                or getattr(user, "fullname", "")
                or user.get_full_name()
                or user.username
            )
            customer_email = customer_email or user.email
            if not customer_mobile:
                from apps.agents.models import Client

                user_client = Client.objects.filter(user=user).first()
                if user_client:
                    customer_mobile = customer_mobile or user_client.mobile
                    customer_pincode = customer_pincode or user_client.pincode

        enquiry_parts = [
            val for val in [service_type, insurance_type, insurance_company] if val
        ]
        enquiry_requirements = " | ".join(enquiry_parts) if enquiry_parts else None

        # Secure URL Calculation
        from apps.agents.models import AgentProfile

        profile = AgentProfile.objects.filter(agent=agent).first()
        url = "#"

        if interaction_type == "whatsapp":
            whatsapp_source = ""
            if profile and profile.whatsapp:
                whatsapp_source = str(profile.whatsapp)
            elif agent.mobile:
                whatsapp_source = str(agent.mobile)

            import re
            import urllib.parse

            whatsapp_digits = re.sub(r"[^0-9]", "", whatsapp_source)
            if len(whatsapp_digits) == 10:
                whatsapp_digits = "91" + whatsapp_digits

            if whatsapp_digits:
                agent_name = (
                    (profile.display_name if profile and profile.display_name else "")
                    or getattr(agent, "fullname", "")
                    or getattr(agent, "get_full_name", lambda: "")()
                    or getattr(agent, "username", "")
                    or "Agent"
                )
                agent_name = agent_name.strip()

                raw_host = request.get_host()
                if raw_host:
                    clean_host = raw_host.split(":")[0]
                    if clean_host in ["127.0.0.1", "localhost"]:
                        domain_name = "localhost"
                    else:
                        domain_name = clean_host
                else:
                    domain_name = "www.padosiagent.com"

                s_type = (service_type or "").strip()
                i_type = (insurance_type or "").strip()
                i_comp = (insurance_company or "").strip()

                if s_type and i_type:
                    req_desc = f"{s_type} for {i_type}"
                elif s_type:
                    req_desc = (
                        s_type
                        if any(
                            w in s_type.lower()
                            for w in ["insurance", "policy", "service"]
                        )
                        else f"{s_type} Service for Insurance"
                    )
                elif i_type:
                    req_desc = f"Insurance Service for {i_type}"
                else:
                    req_desc = "Insurance Service for Insurance"

                if i_comp:
                    req_desc += f" ({i_comp})"

                if customer_pincode:
                    req_desc += f" in {customer_pincode}"

                cust_name = (customer_name or "").strip()
                msg = f"Hello {agent_name},\nI found you on {domain_name}\n\nI am looking for {req_desc}."
                if cust_name:
                    msg += f"\n\nRegards,\n{cust_name}"

                encoded_msg = urllib.parse.quote(msg)
                url = f"https://api.whatsapp.com/send/?phone={whatsapp_digits}&text={encoded_msg}&type=phone_number&app_absent=0"
            else:
                url = "#"

        elif interaction_type == "call":
            url = f"tel:{agent.mobile}" if agent.mobile else "#"

        elif interaction_type in [
            "linkedin",
            "facebook",
            "instagram",
            "youtube",
            "google_business",
        ]:
            social_links = {}
            if profile and profile.social_links:
                if isinstance(profile.social_links, dict):
                    social_links = profile.social_links
                elif isinstance(profile.social_links, str):
                    try:
                        social_links = json_loads(profile.social_links)
                    except ValueError:
                        pass
            url = social_links.get(interaction_type) or "#"

        # Each lead fires Brevo email + FCM + WhatsApp: cap per IP+agent, same limits as
        # agent_card_lead_submit. Over the cap the visitor still gets the link (audit AG4).
        from django.core.cache import cache

        rl_lead_keys = (
            (f"rl_capture_lead_10m_{client_ip}_{agent.id}", 5, 10 * 60),
            (f"rl_capture_lead_day_{client_ip}_{agent.id}", 20, 24 * 60 * 60),
        )
        if any((cache.get(key, 0) or 0) >= limit for key, limit, _window in rl_lead_keys):
            return JsonResponse({"success": True, "duplicate": True, "url": url})

        # Deduplication (1 hour timeframe)
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        existing_lead_query = AgentLead.objects.filter(
            agent_id=agent_id,
            interaction_type=interaction_type,
            created_at__gte=one_hour_ago,
        )

        has_identifier = False
        if customer_mobile:
            existing_lead_query = existing_lead_query.filter(
                customer_mobile=customer_mobile
            )
            has_identifier = True
        elif customer_email:
            existing_lead_query = existing_lead_query.filter(
                customer_email=customer_email
            )
            has_identifier = True

        if has_identifier:
            existing_lead = existing_lead_query.first()
            if existing_lead:
                return JsonResponse({"success": True, "duplicate": True, "url": url})

        # Create Lead
        lead = AgentLead.objects.create(
            agent=agent,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_mobile=customer_mobile,
            customer_pincode=customer_pincode,
            interaction_type=interaction_type,
            lead_status="new",
            service_type=service_type,
            insurance_type=insurance_type,
            insurance_company=insurance_company,
            enquiry_requirements=enquiry_requirements,
            source_page=source_page or "find-agents",
            ip_address=client_ip,
        )

        for key, _limit, window in rl_lead_keys:
            try:
                if not cache.add(key, 1, timeout=window):
                    cache.incr(key)
            except Exception:
                logger.warning("Capture lead rate-limit counter update failed", exc_info=True)

        from apps.wa_agent_bot.services.notification_service import (
            notify_agent_new_lead,
        )

        notify_agent_new_lead(lead)

        # Retrieve device tokens for the agent and dispatch FCM pushes via FcmService
        tokens = list(
            AgentDeviceToken.objects.filter(agent_id=agent_id).values_list(
                "token", flat=True
            )
        )
        tokens = [t for t in tokens if t]

        if tokens:
            title = "New Lead Assigned"
            lead_name = customer_name or "A customer"
            body = f"{lead_name} contacted you via {interaction_type}."

            try:
                from apps.agents.services.fcm import FcmService

                fcm_service = FcmService()
                import threading

                thread = threading.Thread(
                    target=_with_fresh_db(fcm_service.send_to_tokens),
                    args=(
                        tokens,
                        title,
                        body,
                        {
                            "url": "/agent/dashboard",
                            "lead_id": str(lead.id),
                        },
                    ),
                )
                thread.daemon = True
                thread.start()
            except Exception as fcm_err:
                logger.error(f"FCM thread dispatch failed: {fcm_err}")

        # Send email notification to advisor so web-only advisors never miss leads
        if agent and getattr(agent, "email", None):

            def _send_lead_email(
                to_email,
                to_name,
                cust_name,
                cust_phone,
                cust_email,
                int_type,
                serv_type,
                ins_type,
                reqs,
            ):
                try:
                    from apps.agents.services.brevo import email_service

                    lead_label = cust_name or "A prospect"
                    subject = (
                        f"New Client Enquiry: {lead_label} reached out on PadosiAgent"
                    )
                    # Customer-supplied values go into HTML: escape them (audit AG4).
                    from html import escape

                    to_name, cust_name, cust_phone, cust_email, int_type, serv_type, ins_type, reqs = (
                        escape(str(v)) if v else v
                        for v in (to_name, cust_name, cust_phone, cust_email, int_type, serv_type, ins_type, reqs)
                    )
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h2 style="color: #273c8e; margin-top: 0;">🎉 You Have a New Client Lead!</h2>
                        <p>Hello <strong>{to_name}</strong>,</p>
                        <p>A prospective client just reached out to you through your PadosiAgent profile:</p>
                        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Name</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{cust_name or "Not specified"}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Phone</td><td style="padding: 10px; border: 1px solid #e2e8f0;"><a href="tel:{cust_phone or ""}" style="color: #06a441; font-weight: bold;">{cust_phone or "Not specified"}</a></td></tr>
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Email</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{cust_email or "Not specified"}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Interaction Channel</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{int_type or "Direct"}</td></tr>
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Insurance / Service</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{ins_type or serv_type or "General Insurance"}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Details</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{reqs or "Standard inquiry"}</td></tr>
                        </table>
                        <p style="margin-top: 25px;">
                            <a href="{dashboard_url}" style="background-color: #06a441; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View in Dashboard</a>
                        </p>
                        <p style="color: #64748b; font-size: 13px; margin-top: 25px;">Tip: Reach out to your prospective client within 15 minutes for the highest conversion rate!</p>
                    </div>
                    """
                    email_service.send_generic(to_email, to_name, subject, html_content)
                except Exception as mail_err:
                    logger.warning(
                        f"Lead email notification failed for agent {to_email}: {mail_err}"
                    )

            from apps.agents.services.og_urls import get_public_site_base

            dashboard_url = get_public_site_base(request) + "/agent-login/"  # audit AG20

            import threading

            threading.Thread(
                target=_with_fresh_db(_send_lead_email),
                args=(
                    agent.email,
                    agent.fullname or "Advisor",
                    customer_name,
                    customer_mobile,
                    customer_email,
                    interaction_type,
                    service_type,
                    insurance_type,
                    enquiry_requirements,
                ),
                daemon=True,
            ).start()

        return JsonResponse(
            {"success": True, "message": "Lead captured successfully.", "url": url}
        )

    except Exception as e:
        logger.exception(f"Lead capture failed: {e}")
        return JsonResponse(
            {"success": False, "message": "An unexpected error occurred."}, status=500
        )
