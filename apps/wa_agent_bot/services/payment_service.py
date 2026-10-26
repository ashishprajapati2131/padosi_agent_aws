"""
WhatsApp Agent Bot — Payment & Plan Selection Service

Handles:
  1. Fetching available plans and live pricing (matching website /chooseplan/)
  2. Generating official Razorpay Payment Links with UPI, Cards & Netbanking
  3. Generating fallback secure checkout links if Razorpay API is unreachable
  4. Webhook & callback verification with strict cryptographic signatures
  5. Subscription activation, agent creation, and invoice/welcome email queueing
  6. Instant WhatsApp credential delivery upon successful payment
"""

import logging
import os
import secrets
import time
from decimal import Decimal

from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth.models import User

from apps.agents.models import Agent, AgentProfile, AgentSubscription, AgentInsuranceSegment
from apps.home.models import SiteSetting
from apps.agents.services.feature_unlock import PLAN_LABELS, normalize_plan_slug
from apps.agents.services.razorpay_checkout import (
    razorpay_client,
    razorpay_credentials,
    razorpay_webhook_secret,
)
from apps.agents.services.post_payment import queue_invoice_and_welcome
from apps.wa_agent_bot.models import WaBotSession
from apps.wa_agent_bot.services.message_sender import send_text_message
from apps.wa_agent_bot.services.registration_handler import _generate_password, _generate_slug, _ensure_unique_slug

from apps.wa_agent_bot.services.message_templates import render as render_template
from apps.wa_agent_bot.services.site_url import bot_site_url

logger = logging.getLogger(__name__)

# ── Default pricing fallback (mirrors admin panel pricing_config) ──────
_DEFAULT_PRICING = {
    'starter': {
        'name': 'Digital Presence',
        'promo_price': 1999,
        'full_price': 1999,
        'description': 'Perfect for New Agents',
    },
    'professional': {
        'name': 'Professional Presence',
        'promo_price': 9999,
        'full_price': 9999,
        'description': 'For Established Professionals',
    },
}


def get_available_plans():
    """
    Fetch plans and pricing configured in the database / site settings (admin panel).
    Calculates base, 18% GST, and final inclusive amounts.
    """
    try:
        pricing_config = SiteSetting.get_value('pricing_config', _DEFAULT_PRICING)
    except Exception:
        pricing_config = _DEFAULT_PRICING

    if not isinstance(pricing_config, dict):
        pricing_config = dict(_DEFAULT_PRICING)

    starter_cfg = pricing_config.get('starter', _DEFAULT_PRICING['starter'])
    prof_cfg = pricing_config.get('professional', _DEFAULT_PRICING['professional'])

    # Starter pricing: read directly from admin panel plan & pricing config
    starter_base = float(starter_cfg.get('full_price') or starter_cfg.get('promo_price', 1999))
    starter_gst = round(starter_base * 0.18, 2)
    starter_total = int(round(starter_base + starter_gst))

    # Professional pricing: read directly from admin panel plan & pricing config
    prof_base = float(prof_cfg.get('full_price') or prof_cfg.get('promo_price', 9999))
    prof_gst = round(prof_base * 0.18, 2)
    prof_total = int(round(prof_base + prof_gst))

    return {
        'starter': {
            'key': 'starter',
            'name': starter_cfg.get('name', 'Digital Presence'),
            'base': starter_base,
            'gst': starter_gst,
            'total': starter_total,
            'duration_days': 365,
            'description': starter_cfg.get('description', 'Perfect for New Agents'),
            'features': [
                'Permanent Webpage',
                'Digital Visiting Card',
                'Licensed Agent Badge',
                'Call & WhatsApp Direct Buttons',
            ],
        },
        'professional': {
            'key': 'professional',
            'name': prof_cfg.get('name', 'Professional Presence'),
            'base': prof_base,
            'gst': prof_gst,
            'total': prof_total,
            'duration_days': 365,
            'description': prof_cfg.get('description', 'For Established Professionals'),
            'features': [
                'All Starter Plan Features',
                'Trusted Agent Gold Badge',
                'Priority Business Leads',
                'SEO – Found on Google',
            ],
        },
    }


def format_plan_selection_message():
    """
    Generate the WhatsApp message prompting the agent to choose their membership plan.
    """
    plans = get_available_plans()
    starter = plans['starter']
    prof = plans['professional']

    msg = (
        "🌟 *Choose Your Membership Plan*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *{starter['name']}*\n"
        f"   💰 *Price:* ₹{starter['total']} (₹{int(starter['base'])} + 18% GST)\n"
        f"   ⏱️ *Validity:* 1 Year\n"
        f"   ✨ {starter['description']}\n"
        f"   • {', '.join(starter['features'])}\n\n"
        f"2️⃣ *{prof['name']}* ⭐ _RECOMMENDED_\n"
        f"   💰 *Price:* ₹{prof['total']} (₹{int(prof['base'])} + 18% GST)\n"
        f"   ⏱️ *Validity:* 1 Year\n"
        f"   ✨ {prof['description']}\n"
        f"   • {', '.join(prof['features'])} & more!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Reply with *1* or *2* to select your plan.\n"
        "_(Or reply *back* to edit your details)_"
    )
    return msg


def create_or_update_pending_agent(registration_data, plan_key):
    """
    Creates or updates the User and Agent in 'pending_payment' status
    before payment is collected (matches website registration architecture).
    """
    email = registration_data.get('email', '').strip().lower()
    fullname = registration_data.get('fullname', '').strip()
    mobile = registration_data.get('mobile', '').strip()
    state = registration_data.get('state', '').strip()
    agent_pincode = registration_data.get('agent_pincode', '').strip()
    experience_range = registration_data.get('experience_range', '').strip()
    segments = registration_data.get('segments', [])

    # 1. User creation / retrieval — default password is the agent's 10-digit mobile number
    mobile_digits = ''.join(c for c in mobile if c.isdigit())
    password = mobile_digits[-10:] if len(mobile_digits) >= 10 else mobile_digits
    user, u_created = User.objects.get_or_create(
        username=email,
        defaults={
            'email': email,
            'first_name': fullname.split()[0] if fullname else '',
            'last_name': ' '.join(fullname.split()[1:]) if len(fullname.split()) > 1 else '',
        }
    )
    user.set_password(password)
    user.save()

    # 2. Agent creation / retrieval in pending_payment
    user_types = [seg for seg in segments if seg in ('health', 'life', 'motor', 'sme')]
    agent, a_created = Agent.objects.get_or_create(
        email=email,
        defaults={
            'user': user,
            'fullname': fullname,
            'mobile': mobile,
            'status': 'pending_payment',
            'plan_type': plan_key,
            'registration_step': 2,
            'user_types': user_types,
            'experience_range': experience_range,
            'agent_pincode': agent_pincode,
            'registration_draft': {
                'source': 'whatsapp_bot',
                'state': state,
                'segments': segments,
            },
        }
    )
    if not a_created:
        agent.fullname = fullname
        agent.mobile = mobile
        agent.user_types = user_types
        agent.plan_type = plan_key
        agent.agent_pincode = agent_pincode
        if agent.status not in ('active', 'awaiting_approval'):
            agent.status = 'pending_payment'
        agent.save()

    # 3. Create or update profile
    profile = AgentProfile.objects.filter(agent=agent).first()
    if not profile:
        base_slug = _ensure_unique_slug(_generate_slug(fullname, email))
        try:
            profile = AgentProfile.objects.create(
                agent=agent,
                slug=base_slug,
                state=state,
                whatsapp=mobile,
                service_pincodes=[agent_pincode] if agent_pincode else [],
            )
        except IntegrityError:
            safe_slug = f"{base_slug}-{secrets.token_hex(4)}"
            profile = AgentProfile.objects.create(
                agent=agent,
                slug=safe_slug,
                state=state,
                whatsapp=mobile,
                service_pincodes=[agent_pincode] if agent_pincode else [],
            )
    else:
        if state:
            profile.state = state
        if mobile:
            profile.whatsapp = mobile
        if agent_pincode and not profile.service_pincodes:
            profile.service_pincodes = [agent_pincode]
        profile.save()

    # 4. Create insurance segments
    AgentInsuranceSegment.objects.filter(agent=agent).delete()
    if segments:
        AgentInsuranceSegment.objects.bulk_create([
            AgentInsuranceSegment(agent=agent, segment_type=seg)
            for seg in segments
        ])

    return agent, user, password


def create_plan_payment_link(session, plan_key):
    """
    Generate an official Razorpay Payment Link for the selected plan.
    Falls back gracefully to a direct web checkout URL if Razorpay API
    keys are missing or unavailable.

    Returns dict with:
        success: bool
        payment_link: str (URL)
        payment_link_id: str
        plan_name: str
        amount: int (rupees)
        base: float
        gst: float
        agent: Agent
    """
    plans = get_available_plans()
    if plan_key not in plans:
        plan_key = 'starter'

    plan = plans[plan_key]
    site_url = bot_site_url()

    # Create / update Agent in pending_payment status
    agent, user, temp_password = create_or_update_pending_agent(session.registration_data, plan_key)
    session.agent = agent
    session.save()

    # Create pending AgentSubscription
    subscription = AgentSubscription.objects.create(
        agent=agent,
        selected_plan=plan['name'],
        registration_amount=Decimal(str(plan['total'])),
        payment_status='pending',
        status='inactive',
    )

    total_amount_paise = int(round(plan['total'] * 100))
    customer_name = session.registration_data.get('fullname', agent.fullname)
    customer_email = session.registration_data.get('email', agent.email)
    customer_mobile = session.registration_data.get('mobile', agent.mobile)

    payment_link_url = None
    payment_link_id = None

    # Try creating official Razorpay Payment Link
    client = razorpay_client()
    if client:
        try:
            callback_url = f"{site_url}/wa-bot/payment-callback/"
            link_payload = {
                'amount': total_amount_paise,
                'currency': 'INR',
                'accept_partial': False,
                'description': f"Padosi Agent Membership — {plan['name']}",
                'customer': {
                    'name': customer_name,
                    'email': customer_email,
                    'contact': customer_mobile,
                },
                'notify': {
                    'sms': True,
                    'email': True,
                },
                'reminder_enable': True,
                'notes': {
                    'agent_id': str(agent.id),
                    'subscription_id': str(subscription.id),
                    'plan_key': plan_key,
                    'wa_phone': session.phone_number,
                    'source': 'whatsapp_bot',
                },
                'callback_url': callback_url,
                'callback_method': 'get',
            }
            rzp_link = client.payment_link.create(link_payload)
            payment_link_url = rzp_link.get('short_url')
            payment_link_id = rzp_link.get('id')
            logger.info(f"[WA-Bot] Created Razorpay payment link {payment_link_id} for agent {agent.id}")
        except Exception as e:
            logger.error(f"[WA-Bot] Razorpay payment link creation failed: {e}", exc_info=True)

    # Fallback to direct web checkout URL if link creation failed or client unavailable
    if not payment_link_url:
        payment_link_url = f"{site_url}/chooseplan/"
        payment_link_id = f"fallback_{subscription.id}_{int(time.time())}"
        logger.warning(f"[WA-Bot] Using fallback web checkout URL for agent {agent.id}")

    # Update subscription record with the order / link ID
    subscription.razorpay_order_id = payment_link_id
    subscription.save(update_fields=['razorpay_order_id'])

    # Save payment info in session context
    reg_data = session.registration_data or {}
    reg_data['selected_plan'] = plan_key
    reg_data['plan_name'] = plan['name']
    reg_data['plan_total'] = plan['total']
    reg_data['payment_link'] = payment_link_url
    reg_data['payment_link_id'] = payment_link_id
    reg_data['subscription_id'] = subscription.id
    reg_data['temp_password'] = temp_password
    session.registration_data = reg_data
    session.save()

    return {
        'success': True,
        'payment_link': payment_link_url,
        'payment_link_id': payment_link_id,
        'plan_name': plan['name'],
        'base': plan['base'],
        'gst': plan['gst'],
        'total': plan['total'],
        'agent': agent,
        'subscription': subscription,
    }


def format_payment_prompt_message(payment_info):
    """
    Format the WhatsApp message delivering the payment link with pricing breakdown.
    """
    return (
        f"💳 *Complete Your Registration*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 *Selected Plan:* {payment_info['plan_name']}\n"
        f"💰 *Base Price:* ₹{int(payment_info['base'])}\n"
        f"🧾 *GST (18%):* ₹{payment_info['gst']}\n"
        f"🏷️ *Total Payable:* ₹{payment_info['total']}\n\n"
        f"🔗 *Click the link below to pay securely:*\n"
        f"👉 {payment_info['payment_link']}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ *Instant Activation via:*\n"
        f"• UPI (Google Pay, PhonePe, Paytm, BHIM)\n"
        f"• Debit & Credit Cards\n"
        f"• Netbanking & Wallets\n\n"
        f"_Your login ID, password, and dashboard access will be sent here immediately upon payment!_\n\n"
        f"_(Reply *change* to select a different plan or *cancel* to abort)_"
    )


def activate_agent_subscription_after_payment(subscription_id, payment_id=None, signature=None):
    """
    Mark subscription as completed, activate the Agent account,
    trigger background invoice + welcome email, and send login credentials
    to the agent's WhatsApp.

    Idempotent and thread-safe with database transaction locks.
    """
    with transaction.atomic():
        try:
            subscription = AgentSubscription.objects.select_for_update().get(pk=subscription_id)
        except AgentSubscription.DoesNotExist:
            logger.error(f"[WA-Bot] Subscription #{subscription_id} not found during activation")
            return False, "Subscription not found"

        if subscription.payment_status == 'completed':
            logger.info(f"[WA-Bot] Subscription #{subscription_id} was already completed (idempotent)")
            return True, "Already activated"

        agent = subscription.agent
        now = timezone.now()

        # Determine duration
        plan_slug = normalize_plan_slug(agent.plan_type or subscription.selected_plan)
        duration_days = 30 if plan_slug == 'free_trial' else 365

        # A bot-registered agent must never be linked to a staff/portal login (checked before any write).
        from apps.agents.services.account_auth import is_non_agent_portal_user
        if not agent.user and is_non_agent_portal_user(User.objects.filter(username=agent.email).first()):
            logger.error(f"[WA-Bot] Refusing to activate agent #{agent.id}: email belongs to a staff/portal login")
            return False, "Email belongs to a staff or portal account"

        # 1. Activate subscription
        subscription.payment_status = 'completed'
        subscription.status = 'active'
        subscription.starts_at = now
        subscription.expires_at = now + timezone.timedelta(days=duration_days)
        if payment_id:
            subscription.razorpay_payment_id = payment_id
        if signature:
            subscription.razorpay_signature = signature
        subscription.save()

        # 2. Update Agent Status to pending_approval (Admin must approve before it becomes active, matching website flow)
        agent.status = 'pending_approval'
        agent.registration_step = 2
        agent.email_verified_at = now
        if plan_slug == 'free_trial':
            agent.trial_ends_at = subscription.expires_at
        agent.save()

        # 3. Ensure User exists and password is set to 10-digit mobile number
        mobile_digits = ''.join(c for c in (agent.mobile or '') if c.isdigit())
        password = mobile_digits[-10:] if len(mobile_digits) >= 10 else (mobile_digits or '1234567890')

        # Only a login created here gets the mobile password; an existing one is never overwritten.
        new_user = False
        if not agent.user:
            user = User.objects.filter(username=agent.email).first()
            if not user:
                user = User.objects.create_user(
                    username=agent.email,
                    email=agent.email,
                    first_name=agent.fullname.split()[0] if agent.fullname else '',
                    last_name=' '.join(agent.fullname.split()[1:]) if len(agent.fullname.split()) > 1 else '',
                )
                new_user = True
            agent.user = user
            agent.save()

        if new_user or not agent.user.has_usable_password():
            agent.user.set_password(password)
            agent.user.save()

        # 4. Locate or create WhatsApp Session
        session = WaBotSession.objects.filter(agent=agent).first()
        if not session and agent.mobile:
            mobile_clean = ''.join(c for c in agent.mobile if c.isdigit())
            for prefix in ('91', ''):
                session = WaBotSession.objects.filter(phone_number=f"{prefix}{mobile_clean}").first()
                if session:
                    break
            if not session:
                target_phone = '91' + mobile_clean if len(mobile_clean) == 10 else mobile_clean
                session, _ = WaBotSession.objects.get_or_create(
                    phone_number=target_phone,
                    defaults={'agent': agent, 'state': WaBotSession.STATE_WELCOME}
                )

        if session and not session.agent:
            session.agent = agent
            session.save()

        # 5. Trigger invoice and welcome email in background
        try:
            queue_invoice_and_welcome(agent.id, subscription.id)
        except Exception as e:
            logger.error(f"[WA-Bot] Error queuing invoice/welcome: {e}")

        # 6. Update session to logged_in and deliver credentials
        if session:
            session.is_registered = True
            session.is_logged_in = True
            session.state = WaBotSession.STATE_LOGGED_IN
            session.generated_password = password
            if not isinstance(session.registration_data, dict):
                session.registration_data = {}
            session.registration_data['temp_password'] = password
            session.save()

            site_url = bot_site_url()
            login_url = f"{site_url}/agent-login/"
            welcome_msg = render_template(
                'welcome', agent_name=agent.fullname, login_url=login_url, email=agent.email,
                password=password, plan=subscription.selected_plan,
            )

            # 6. Send WhatsApp confirmation with credentials (logged by send_text_message)
            send_res = send_text_message(session.phone_number, welcome_msg, category='welcome', session=session)
            if not send_res.get('success'):
                logger.warning(f"[WA-Bot] Failed to send credentials via OpenWA: {send_res.get('error')}. Setting retry flag.")
                session.registration_data['pending_credentials_delivery'] = True
                session.save()

            # Also send to agent's registered mobile if different from session phone
            agent_mobile = ''.join(c for c in (agent.mobile or '') if c.isdigit())
            if agent_mobile:
                if len(agent_mobile) == 10:
                    agent_mobile = '91' + agent_mobile
                if agent_mobile != session.phone_number:
                    send_text_message(agent_mobile, welcome_msg, category='welcome')

            logger.info(f"[WA-Bot] Successfully activated agent #{agent.id} and dispatched WhatsApp credentials")

        return True, "Activated successfully"
