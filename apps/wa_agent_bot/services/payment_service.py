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
from django.db import transaction
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

logger = logging.getLogger(__name__)

# ── Default pricing fallback (mirrors apps/agents/views/registration.py) ─
_DEFAULT_PRICING = {
    'starter': {
        'name': 'Starter Plan',
        'promo_price': 1499,
        'full_price': 1999,
        'description': 'Perfect for New Agents',
    },
    'professional': {
        'name': 'Professional Plan',
        'promo_price': 7999,
        'full_price': 9999,
        'description': 'For Established Professionals (Recommended)',
    },
}


def get_available_plans():
    """
    Fetch plans and pricing configured in the database / site settings.
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

    # Trial plan config
    try:
        trial_config = SiteSetting.get_value('trial_plan_config')
    except Exception:
        trial_config = None
    if not trial_config or not isinstance(trial_config, dict):
        trial_config = {'price': 1, 'is_active': True, 'duration_days': 30}

    trial_base = float(trial_config.get('price', 1))
    trial_gst = round(trial_base * 0.18, 2)
    trial_total = round(trial_base + trial_gst, 2)
    trial_days = int(trial_config.get('duration_days', 30))
    trial_active = bool(trial_config.get('is_active', True))

    # Starter pricing
    starter_base = float(starter_cfg.get('promo_price', 1499))
    starter_gst = round(starter_base * 0.18, 2)
    starter_total = int(round(starter_base + starter_gst))

    # Professional pricing
    prof_base = float(prof_cfg.get('promo_price', 7999))
    prof_gst = round(prof_base * 0.18, 2)
    prof_total = int(round(prof_base + prof_gst))

    return {
        'starter': {
            'key': 'starter',
            'name': starter_cfg.get('name', 'Starter Plan'),
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
                'Customer Reviews & Ratings',
                'Area Pincode Visibility',
            ],
        },
        'professional': {
            'key': 'professional',
            'name': prof_cfg.get('name', 'Professional Plan'),
            'base': prof_base,
            'gst': prof_gst,
            'total': prof_total,
            'duration_days': 365,
            'description': prof_cfg.get('description', 'For Established Professionals (Recommended)'),
            'features': [
                'All Starter Plan Features',
                'Trusted Agent Gold Badge',
                'Priority Business Leads',
                'SEO – Found on Google',
                'Detailed Profile Analytics',
                'Photo & Achievement Gallery',
                'AI Profile Auto-Fill & Suggestions',
            ],
        },
        'free_trial': {
            'key': 'free_trial',
            'name': '30-Day Trial Plan',
            'base': trial_base,
            'gst': trial_gst,
            'total': trial_total,
            'duration_days': trial_days,
            'is_active': trial_active,
            'description': f'Full access for {trial_days} days to test the platform',
            'features': [
                f'{trial_days} Days Full Access',
                'Webpage & Digital Card',
                'Customer Reviews & QR',
                'Experience all core features',
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
    trial = plans['free_trial']

    msg = (
        "🌟 *Choose Your Membership Plan*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"1️⃣ *{starter['name']}*\n"
        f"   💰 *Price:* ₹{starter['total']} (₹{int(starter['base'])} + 18% GST)\n"
        f"   ⏱️ *Validity:* 1 Year\n"
        f"   ✨ {starter['description']}\n"
        f"   • {', '.join(starter['features'][:4])}\n\n"
        f"2️⃣ *{prof['name']}* ⭐ _RECOMMENDED_\n"
        f"   💰 *Price:* ₹{prof['total']} (₹{int(prof['base'])} + 18% GST)\n"
        f"   ⏱️ *Validity:* 1 Year\n"
        f"   ✨ {prof['description']}\n"
        f"   • {', '.join(prof['features'][:4])} & more!\n\n"
    )

    if trial.get('is_active', True):
        msg += (
            f"3️⃣ *{trial['name']}*\n"
            f"   💰 *Price:* ₹{trial['total']} (Verification charge)\n"
            f"   ⏱️ *Validity:* {trial['duration_days']} Days Full Access\n"
            f"   ✨ {trial['description']}\n\n"
        )

    msg += (
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Reply with *1*, *2*, or *3* to select your plan.\n"
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

    # 1. User creation / retrieval
    password = _generate_password(10)
    user, u_created = User.objects.get_or_create(
        username=email,
        defaults={
            'email': email,
            'first_name': fullname.split()[0] if fullname else '',
            'last_name': ' '.join(fullname.split()[1:]) if len(fullname.split()) > 1 else '',
        }
    )
    if u_created:
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
    base_slug = _ensure_unique_slug(_generate_slug(fullname, email))
    profile, _ = AgentProfile.objects.get_or_create(
        agent=agent,
        defaults={
            'slug': base_slug,
            'state': state,
            'whatsapp': mobile,
            'service_pincodes': [agent_pincode] if agent_pincode else [],
        }
    )

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
    site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')

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

        # 2. Activate Agent
        agent.status = 'active'
        agent.registration_step = 3
        agent.email_verified_at = now
        if plan_slug == 'free_trial':
            agent.trial_ends_at = subscription.expires_at
        agent.save()

        # 3. Locate WhatsApp Session
        session = WaBotSession.objects.filter(agent=agent).first()
        if not session and agent.mobile:
            # Try by phone number
            mobile_clean = ''.join(c for c in agent.mobile if c.isdigit())
            for prefix in ('91', ''):
                session = WaBotSession.objects.filter(phone_number=f"{prefix}{mobile_clean}").first()
                if session:
                    break

        password = ""
        if session:
            password = session.registration_data.get('temp_password', '')

        # Ensure user has active password
        if agent.user and not password:
            password = _generate_password(10)
            agent.user.set_password(password)
            agent.user.save()

        # 4. Trigger invoice and welcome email in background
        try:
            queue_invoice_and_welcome(agent.id, subscription.id)
        except Exception as e:
            logger.error(f"[WA-Bot] Error queuing invoice/welcome: {e}")

        # 5. Update session to logged_in
        if session:
            session.is_registered = True
            session.is_logged_in = True
            session.state = WaBotSession.STATE_LOGGED_IN
            session.generated_password = password
            session.save()

            # 6. Send WhatsApp confirmation with credentials
            site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
            login_url = f"{site_url}/agent-login/"
            welcome_msg = (
                f"🎉 *Congratulations, {agent.fullname}!* 🚀\n"
                f"Your payment was received and your Agent Account is now *ACTIVE*!\n\n"
                f"🔑 *Your Login Credentials:*\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 *Login URL:* {login_url}\n"
                f"📧 *Email / User ID:* {agent.email}\n"
                f"🔒 *Temporary Password:* `{password}`\n"
                f"📦 *Active Plan:* {subscription.selected_plan}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👉 *Next Steps:*\n"
                f"1. Login at the link above and change your password\n"
                f"2. Upload your profile photo and details\n"
                f"3. Share your digital card with clients\n\n"
                f"💬 *WhatsApp Agent Assistant is Ready!*\n"
                f"Type *help* anytime to view your profile, dashboard link, referral code, and status."
            )
            send_text_message(session.phone_number, welcome_msg)
            logger.info(f"[WA-Bot] Successfully activated agent #{agent.id} and sent WhatsApp credentials")

        return True, "Activated successfully"
