"""Agent QR preview/download and public card landing."""
import logging
import re

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.agents.models import Agent
from apps.agents.services.qr_branded import get_or_create_qr_png
from apps.agents.services.review_growth import QR_TYPE_LABELS, QR_TYPES, is_qr_enabled, qr_access_for_plan
from apps.agents.views.dashboard import _resolve_agent_plan

logger = logging.getLogger(__name__)


def _resolve_agent_by_slug(slug):
    agent = Agent.objects.filter(profile__slug=slug).first()
    if not agent and str(slug).isdigit():
        agent = Agent.objects.filter(id=int(slug)).first()
    return agent


def _logged_in_agent(request):
    from apps.agents.services.account_auth import resolve_agent_for_user
    return resolve_agent_for_user(request.user)


def _png_response(png_bytes, filename, download=False):
    response = HttpResponse(png_bytes, content_type='image/png')
    disposition = 'attachment' if download else 'inline'
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '-', filename).strip('-') or 'qr.png'
    response['Content-Disposition'] = f'{disposition}; filename="{safe_name}"'
    response['Cache-Control'] = 'public, max-age=3600' if not download else 'private, no-store'
    return response


@login_required(login_url='agents:agent_login')
@require_GET
def agent_qr_image(request, qr_type):
    if qr_type not in QR_TYPES or not is_qr_enabled():
        raise Http404('QR service is not available')
    agent = _logged_in_agent(request)
    if not agent:
        raise Http404('Agent not found')
    plan = _resolve_agent_plan(agent.plan_type, agent=agent)
    if not qr_access_for_plan(plan):
        raise Http404('QR service is not available')
    png = get_or_create_qr_png(request, agent, qr_type)
    if not png:
        raise Http404('Could not generate QR code')
    slug = getattr(agent, 'agent_slug', None) or str(agent.id)
    return _png_response(png, f'PadosiAgent-{slug}-{qr_type}.png')


@login_required(login_url='agents:agent_login')
@require_GET
def agent_qr_download(request, qr_type):
    if qr_type not in QR_TYPES:
        raise Http404('QR download is not available')
    agent = _logged_in_agent(request)
    if not agent:
        raise Http404('Agent not found')
    plan = _resolve_agent_plan(agent.plan_type, agent=agent)
    if not qr_access_for_plan(plan, download=True):
        raise Http404('QR download is not available')
    png = get_or_create_qr_png(request, agent, qr_type)
    if not png:
        raise Http404('Could not generate QR code')
    slug = getattr(agent, 'agent_slug', None) or str(agent.id)
    return _png_response(png, f'PadosiAgent-{slug}-{qr_type}.png', download=True)


@require_GET
def public_qr_image(request, slug, qr_type):
    if qr_type not in QR_TYPES or not is_qr_enabled():
        raise Http404('QR service is not available')
    agent = _resolve_agent_by_slug(slug)
    if not agent:
        raise Http404('Agent not found')
    plan = _resolve_agent_plan(agent.plan_type, agent=agent)
    if not qr_access_for_plan(plan):
        raise Http404('QR service is not available')
    png = get_or_create_qr_png(request, agent, qr_type)
    if not png:
        raise Http404('Could not generate QR code')
    return _png_response(png, f'PadosiAgent-{slug}-{qr_type}.png')


@require_GET
def public_agent_card(request, slug):
    from django.http import Http404 as _Http404
    from apps.home.models import SiteSetting
    import json
    import urllib.parse

    # Master Admin ON/OFF Feature Flag
    raw_flag = SiteSetting.get_value('agent_digital_card_enabled', True)
    card_feature_enabled = str(raw_flag).strip().lower() not in ('0', 'false', 'no', 'off', '')
    if not card_feature_enabled:
        return render(request, 'agents/profile_unavailable.html', status=404)

    agent = _resolve_agent_by_slug(slug)
    if not agent:
        raise _Http404('Agent not found')
    profile = agent.get_primary_profile()
    if profile is None:
        raise _Http404('Agent profile not found')

    is_visible = bool(getattr(profile, 'is_profile_visible', False) or getattr(profile, 'is_card_visible', False))
    if agent.status in ('inactive', 'suspended', 'deleted') or not is_visible:
        return render(request, 'agents/profile_unavailable.html', {
            'agent': agent,
            'profile': profile,
        }, status=404)

    agent_plan = _resolve_agent_plan(agent.plan_type, agent=agent)
    display_name = (profile.display_name if profile else '') or agent.fullname or 'Agent'
    agent_slug = getattr(profile, 'slug', None) or getattr(agent, 'agent_slug', None) or str(slug)

    # Clean phone numbers
    mobile_raw = str(getattr(agent, 'mobile', '') or getattr(profile, 'whatsapp', '') or '').strip()
    whatsapp_raw = str(getattr(profile, 'whatsapp', '') or getattr(agent, 'mobile', '') or '').strip()

    mobile_digits = re.sub(r'[^0-9]', '', mobile_raw)
    whatsapp_digits = re.sub(r'[^0-9]', '', whatsapp_raw)
    if len(whatsapp_digits) == 10:
        whatsapp_digits = '91' + whatsapp_digits

    # Pre-filled WhatsApp message
    wa_greeting = urllib.parse.quote(
        f"Hello {display_name},\nI found your Digital Visiting Card on PadosiAgent and would like to connect for insurance advice."
    )
    whatsapp_url = f"https://api.whatsapp.com/send?phone={whatsapp_digits}&text={wa_greeting}" if whatsapp_digits else ""
    call_url = f"tel:+91{mobile_digits[-10:]}" if len(mobile_digits) >= 10 else (f"tel:{mobile_digits}" if mobile_digits else "")

    # Office address & Google Maps direction link
    office_address = (getattr(profile, 'office_address', '') or getattr(profile, 'address', '') or '').strip()
    state_name = getattr(profile, 'state', None) or getattr(agent, 'state', None) or 'Gujarat'
    pincode = getattr(agent, 'agent_pincode', '') or getattr(profile, 'pincode', '') or ''
    maps_query = office_address or f"{state_name} {pincode}".strip()
    google_maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(maps_query)}" if maps_query else ""

    # Experience & Profession
    exp_years = profile.experience_years or getattr(agent, 'experience_range', '') or ''
    profession = getattr(agent, 'profession', '') or 'Certified Insurance & Financial Advisor'

    # Languages
    raw_langs = getattr(profile, 'languages', '') or ''
    if isinstance(raw_langs, str):
        languages_list = [l.strip().title() for l in raw_langs.split(',') if l.strip()]
    elif isinstance(raw_langs, (list, tuple)):
        languages_list = [str(l).strip().title() for l in raw_langs if str(l).strip()]
    else:
        languages_list = []

    # Social links parsing (only retain non-empty valid URLs)
    social_links_raw = profile.social_links or {}
    if isinstance(social_links_raw, str):
        try:
            social_links_raw = json.loads(social_links_raw)
        except Exception:
            social_links_raw = {}
    social_links = {}
    for k, v in (social_links_raw or {}).items():
        if v and str(v).strip() and str(v).strip() != '#' and str(v).strip().lower() != 'none':
            social_links[k] = str(v).strip()

    # Specialties / Insurance segments
    specialties = []
    try:
        specialties = list(agent.ordered_insurance_segments or [])
    except Exception:
        specialties = []

    # Rating & Reviews
    try:
        avg_rating = round(float(agent.average_rating or 5.0), 1)
    except Exception:
        avg_rating = 5.0
    try:
        reviews_count = int(agent.review_count or agent.reviews.filter(is_approved=True).count())
    except Exception:
        reviews_count = 0

    # Verified Performance Stats
    perf = getattr(agent, 'performanceStats', None)
    claims_settled_raw = getattr(perf, 'claims_settled', None) if perf else None
    claims_settled_val = None
    if claims_settled_raw is not None:
        try:
            parsed_claims = int(str(claims_settled_raw).strip())
            if parsed_claims > 0:
                claims_settled_val = parsed_claims
        except (ValueError, TypeError):
            claims_settled_val = None

    has_verified_claims = bool(claims_settled_val and claims_settled_val > 0)
    claims_settled = claims_settled_val

    claims_rate_raw = getattr(perf, 'success_rate', None) if perf else None
    claims_rate = 100
    if claims_rate_raw is not None:
        try:
            claims_rate = int(float(str(claims_rate_raw).replace('%', '').strip()))
        except (ValueError, TypeError):
            claims_rate = 100

    response_time_val = getattr(perf, 'response_time', None) if perf else None

    state_code = getattr(profile, 'state_code', 'gj')
    try:
        full_profile_url = reverse('agents:agent_public_profile_state_direct', kwargs={'state_code': state_code, 'slug': agent_slug})
    except Exception:
        full_profile_url = f"/{state_code}/{agent_slug}/"

    card_url = request.build_absolute_uri(reverse('agents:agent_public_card', kwargs={'slug': agent_slug}))

    from apps.agents.services.og_meta import profile_og_context

    ctx = {
        'agent': agent,
        'profile': profile,
        'agent_plan': agent_plan,
        'agentDisplayName': display_name,
        'agent_slug': agent_slug,
        'qr_type_label': QR_TYPE_LABELS['card'],
        'mobile_number': mobile_raw,
        'whatsapp_number': whatsapp_raw,
        'call_url': call_url,
        'whatsapp_url': whatsapp_url,
        'google_maps_url': google_maps_url,
        'office_address': office_address,
        'state': state_name,
        'pincode': pincode,
        'experience_years': exp_years,
        'profession': profession,
        'languages_list': languages_list,
        'social_links': social_links,
        'specialties': specialties,
        'average_rating': avg_rating,
        'reviews_count': reviews_count,
        'has_reviews': (reviews_count > 0),
        'performance': perf,
        'has_verified_claims': has_verified_claims,
        'claims_settled': claims_settled,
        'claims_rate': claims_rate,
        'response_time_val': response_time_val,
        'brand_logo_url': _brand_logo_url(),
        'vcard_url': reverse('agents:agent_card_vcf', kwargs={'slug': agent_slug}),
        'lead_submit_url': reverse('agents:agent_card_lead_submit', kwargs={'slug': agent_slug}),
        'card_qr_url': reverse('agents:agent_public_qr_image', kwargs={'slug': agent_slug, 'qr_type': 'card'}),
        'full_profile_url': full_profile_url,
        'review_url': reverse('agents:agent_public_review', kwargs={'slug': agent_slug}),
        'card_share_url': card_url,
        'card_share_title': f"{display_name} — Certified Insurance Advisor | PadosiAgent",
        'card_share_text': f"Connect with {display_name}, Certified Insurance Advisor on PadosiAgent: {card_url}",
        'hide_header': True,
        'hide_footer': True,
        'hide_chatbot': True,
    }
    ctx.update(profile_og_context(request, agent, display_name=display_name))
    return render(request, 'agents/public_agent_card.html', ctx)


@require_GET
def agent_card_vcf_download(request, slug):
    """Download RFC 2426 vCard 3.0 file for 1-Tap Save to Phone Contacts."""
    from apps.home.models import SiteSetting
    raw_flag = SiteSetting.get_value('agent_digital_card_enabled', True)
    if str(raw_flag).strip().lower() in ('0', 'false', 'no', 'off', ''):
        raise Http404('Digital Card is disabled')

    agent = _resolve_agent_by_slug(slug)
    if not agent:
        raise Http404('Agent not found')
    profile = agent.get_primary_profile()
    if profile is None:
        raise Http404('Agent profile not found')

    name = (profile.display_name if profile else '') or agent.fullname or 'Insurance Advisor'
    parts = name.strip().split(' ', 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ''

    mobile = getattr(agent, 'mobile', '') or getattr(profile, 'whatsapp', '') or ''
    email = getattr(agent, 'email', '') or ''
    agency = getattr(profile, 'agency_name', '') or 'PadosiAgent'
    address = getattr(profile, 'office_address', '') or getattr(profile, 'address', '') or ''
    city = getattr(agent, 'city', '') or ''
    state = getattr(agent, 'state', '') or ''
    pincode = getattr(agent, 'agent_pincode', '') or getattr(profile, 'pincode', '') or ''
    license_no = getattr(profile, 'license_number', '') or ''

    state_code = getattr(profile, 'state_code', 'gj')
    agent_slug = getattr(profile, 'slug', None) or getattr(agent, 'agent_slug', None) or str(slug)
    try:
        profile_url = request.build_absolute_uri(
            reverse('agents:agent_public_profile_state_direct', kwargs={'state_code': state_code, 'slug': agent_slug})
        )
    except Exception:
        profile_url = request.build_absolute_uri(f'/{state_code}/{agent_slug}/')

    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN;CHARSET=UTF-8:{name}",
        f"N;CHARSET=UTF-8:{last_name};{first_name};;;",
        f"ORG;CHARSET=UTF-8:{agency}",
        "TITLE;CHARSET=UTF-8:Certified Insurance Advisor",
    ]
    if mobile:
        lines.append(f"TEL;TYPE=CELL,VOICE;CHARSET=UTF-8:{mobile}")
        lines.append(f"TEL;TYPE=WORK,VOICE;CHARSET=UTF-8:{mobile}")
    if email:
        lines.append(f"EMAIL;TYPE=PREF,INTERNET:{email}")
    if profile_url:
        lines.append(f"URL;CHARSET=UTF-8:{profile_url}")
    if address or city or state or pincode:
        lines.append(f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{address};{city};{state};{pincode};India")
    note_parts = ["Registered Insurance Advisor on PadosiAgent"]
    if license_no:
        note_parts.append(f"IRDAI License: {license_no}")
    lines.append(f"NOTE;CHARSET=UTF-8:{' | '.join(note_parts)}")
    lines.append("END:VCARD")

    vcf_content = "\r\n".join(lines) + "\r\n"
    response = HttpResponse(vcf_content.encode('utf-8'), content_type='text/vcard; charset=utf-8')
    safe_name = re.sub(r'[^A-Za-z0-9_-]+', '-', agent_slug).strip('-') or 'advisor'
    response['Content-Disposition'] = f'attachment; filename="PadosiAgent-{safe_name}.vcf"'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def agent_card_lead_submit(request, slug):
    """Direct Lead Enquiry Submission from Agent Smart Digital Visiting Card."""
    from django.http import JsonResponse
    from apps.home.models import SiteSetting
    from apps.agents.models import AgentLead, AgentDeviceToken
    from django.utils import timezone
    from apps.admin_panel.middleware import ThreatMonitorMiddleware, is_ip_blocked

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    raw_flag = SiteSetting.get_value('agent_digital_card_enabled', True)
    if str(raw_flag).strip().lower() in ('0', 'false', 'no', 'off', ''):
        return JsonResponse({'success': False, 'message': 'Digital Card enquiry is currently disabled.'}, status=403)

    agent = _resolve_agent_by_slug(slug)
    if not agent:
        return JsonResponse({'success': False, 'message': 'Agent not found.'}, status=404)

    client_ip = ThreatMonitorMiddleware.get_client_ip(request)
    if is_ip_blocked(client_ip):
        return JsonResponse({'success': False, 'message': 'Access denied.'}, status=403)

    customer_name = (request.POST.get('customer_name') or request.POST.get('name') or '').strip()
    customer_mobile = (request.POST.get('customer_mobile') or request.POST.get('mobile') or request.POST.get('contact') or '').strip()
    customer_email = (request.POST.get('customer_email') or request.POST.get('email') or '').strip()
    customer_pincode = (request.POST.get('customer_pincode') or request.POST.get('pincode') or '').strip()
    insurance_type = (request.POST.get('insurance_type') or '').strip()
    service_type = (request.POST.get('service_type') or request.POST.get('requirement') or '').strip()
    message = (request.POST.get('message') or request.POST.get('notes') or '').strip()

    if not customer_name:
        return JsonResponse({'success': False, 'message': 'Please enter your full name.'}, status=400)

    clean_mobile = re.sub(r'[^0-9]', '', customer_mobile)
    if len(clean_mobile) < 10:
        return JsonResponse({'success': False, 'message': 'Please enter a valid 10-digit mobile number.'}, status=400)
    if len(clean_mobile) > 10 and clean_mobile.startswith('91'):
        clean_mobile = clean_mobile[-10:]

    # Deduplication (10 minute window for same mobile + agent)
    ten_mins_ago = timezone.now() - timezone.timedelta(minutes=10)
    if AgentLead.objects.filter(agent=agent, customer_mobile=clean_mobile, created_at__gte=ten_mins_ago).exists():
        return JsonResponse({
            'success': True,
            'message': 'We have already received your enquiry. The advisor will connect with you shortly!',
            'already_submitted': True
        })

    enquiry_reqs_parts = []
    if service_type:
        enquiry_reqs_parts.append(f"Requirement: {service_type}")
    if insurance_type:
        enquiry_reqs_parts.append(f"Insurance: {insurance_type}")
    if message:
        enquiry_reqs_parts.append(f"Message: {message}")
    enquiry_requirements = " | ".join(enquiry_reqs_parts) if enquiry_reqs_parts else "Digital Card Enquiry"

    lead = AgentLead.objects.create(
        agent=agent,
        customer_name=customer_name,
        customer_mobile=clean_mobile,
        customer_email=customer_email or None,
        customer_pincode=customer_pincode or None,
        insurance_type=insurance_type or 'General Insurance',
        service_type=service_type or 'Enquiry',
        enquiry_requirements=enquiry_requirements,
        interaction_type='digital_card_enquiry',
        lead_status='new',
        source_page='digital-card',
        ip_address=client_ip
    )

    # Dispatch FCM push notification to agent devices
    try:
        tokens = list(AgentDeviceToken.objects.filter(agent_id=agent.id).values_list('token', flat=True))
        tokens = [t for t in tokens if t]
        if tokens:
            from apps.agents.services.fcm import FcmService
            import threading
            title = 'New Lead via Digital Visiting Card! 📇'
            body = f"{customer_name} ({clean_mobile}) is inquiring about {insurance_type or 'Insurance'}."
            thread = threading.Thread(
                target=FcmService().send_to_tokens,
                args=(tokens, title, body, {
                    'url': '/agent/dashboard',
                    'lead_id': str(lead.id),
                })
            )
            thread.daemon = True
            thread.start()
    except Exception as e:
        logger.error(f"FCM push notification failed for card lead: {e}")

    # Dispatch email notification to advisor in background thread
    if getattr(agent, 'email', None):
        try:
            from apps.agents.services.brevo import email_service
            import threading
            def _send_lead_email():
                try:
                    subject = f"New Client Enquiry: {customer_name} via Digital Visiting Card"
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
                        <h2 style="color: #0b1f4d; margin-top: 0;">📇 New Lead via Digital Visiting Card!</h2>
                        <p>Hello <strong>{agent.fullname or 'Advisor'}</strong>,</p>
                        <p>A client submitted an enquiry through your Smart Digital Visiting Card on PadosiAgent:</p>
                        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Name</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{customer_name}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Phone</td><td style="padding: 10px; border: 1px solid #e2e8f0;"><a href="tel:+91{clean_mobile}" style="color: #10b981; font-weight: bold;">+91 {clean_mobile}</a></td></tr>
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Pincode</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{customer_pincode or 'Not specified'}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Insurance Type</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{insurance_type or 'General Insurance'}</td></tr>
                            <tr style="background-color: #f8fafc;"><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Requirement</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{service_type or 'Enquiry'}</td></tr>
                            <tr><td style="padding: 10px; font-weight: bold; border: 1px solid #e2e8f0;">Message</td><td style="padding: 10px; border: 1px solid #e2e8f0;">{message or 'None'}</td></tr>
                        </table>
                    </div>
                    """
                    email_service.send_generic(agent.email, agent.fullname or 'Advisor', subject, html_content)
                except Exception as mail_err:
                    logger.warning(f"Card lead email dispatch failed: {mail_err}")
            m_thread = threading.Thread(target=_send_lead_email)
            m_thread.daemon = True
            m_thread.start()
        except Exception:
            pass

    advisor_name = agent.fullname or 'the advisor'
    return JsonResponse({
        'success': True,
        'message': f'Thank you {customer_name}! Your enquiry has been received. {advisor_name} will get in touch with you shortly.',
        'lead_id': lead.id
    })


def _brand_logo_url():
    from django.templatetags.static import static
    from apps.home.models import SiteSetting

    logo = str(SiteSetting.get_value('site_logo', '') or '').strip()
    if logo.startswith('http://') or logo.startswith('https://') or logo.startswith('/'):
        return logo
    if logo:
        return logo if logo.startswith('static/') else f'/static/{logo.lstrip("/")}'
    return static('img/logo.png')


def advisor_review_context(request, agent):
    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else None
    slug = (getattr(profile, 'slug', None) if profile else None) or getattr(agent, 'agent_slug', None) or str(agent.id)
    name = (getattr(profile, 'display_name', None) if profile else None) or agent.fullname or 'Insurance Advisor'
    photo = ''
    if profile:
        photo = getattr(profile, 'profile_photo_url', '') or ''
    if not photo:
        from django.templatetags.static import static as static_url
        photo = static_url('img/avatar-icon.jpg')
    designation = 'Insurance Advisor'
    if profile and getattr(profile, 'agency_name', None):
        designation = f"Insurance Advisor · {profile.agency_name}"
    review_url = request.build_absolute_uri(
        reverse('agents:agent_public_review', kwargs={'slug': slug})
    )
    display_host = review_url.replace('https://', '').replace('http://', '').rstrip('/')
    return {
        'agent': agent,
        'profile': profile,
        'advisor_name': name,
        'advisor_designation': designation,
        'advisor_image': photo,
        'advisor_slug': slug,
        'review_url': review_url,
        'review_url_display': display_host,
        'brand_logo_url': _brand_logo_url(),
        'hide_header': True,
        'hide_footer': True,
    }


@require_GET
def public_review_page(request, slug):
    agent = _resolve_agent_by_slug(slug)
    if not agent:
        raise Http404('Agent not found')
    profile = agent.get_primary_profile()
    if profile is None:
        raise Http404('Agent profile not found')
    is_visible = bool(getattr(profile, 'is_profile_visible', False) or getattr(profile, 'is_card_visible', False))
    if agent.status in ('inactive', 'suspended', 'deleted') or not is_visible:
        return render(request, 'agents/profile_unavailable.html', {
            'agent': agent,
            'profile': profile,
        }, status=404)

    context = advisor_review_context(request, agent)
    context.update({
        'hide_header': False,
        'hide_footer': False,
        'review_post_url': reverse('agents:agent_store_review', kwargs={'slug': context['advisor_slug']}),
        'is_guest': not request.user.is_authenticated,
    })
    return render(request, 'agents/public_review.html', context)


@require_GET
def public_review_card(request, slug):
    agent = _resolve_agent_by_slug(slug)
    if not agent:
        raise Http404('Agent not found')
    profile = agent.get_primary_profile()
    if profile is None:
        raise Http404('Agent profile not found')
    is_visible = bool(getattr(profile, 'is_profile_visible', False) or getattr(profile, 'is_card_visible', False))
    owner = _logged_in_agent(request)
    is_owner = bool(owner and owner.id == agent.id)
    if not is_owner and (agent.status in ('inactive', 'suspended', 'deleted') or not is_visible):
        return render(request, 'agents/profile_unavailable.html', {
            'agent': agent,
            'profile': profile,
        }, status=404)
    context = advisor_review_context(request, agent)
    context['is_owner'] = is_owner
    return render(request, 'agents/review_card.html', context)


@login_required(login_url='agents:agent_login')
@require_GET
def agent_review_card_redirect(request):
    from django.shortcuts import redirect
    from django.urls import reverse

    agent = _logged_in_agent(request)
    if not agent:
        raise Http404('Agent not found')
    slug = getattr(agent, 'agent_slug', None) or str(agent.id)
    return redirect(reverse('agents:agent_review_card', kwargs={'slug': slug}))
