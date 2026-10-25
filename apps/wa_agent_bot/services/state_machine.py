"""
WhatsApp Agent Bot — Conversation State Machine

The heart of the bot. Routes incoming messages to the correct handler
based on the current conversation state, validates input, advances
the state, and generates reply messages.

State flow:
  WELCOME → ASK_FULLNAME → ASK_EMAIL → ASK_MOBILE → ASK_STATE →
  ASK_PINCODE → ASK_EXPERIENCE → ASK_SEGMENTS → CONFIRM_DETAILS →
  CREATING_ACCOUNT → REGISTRATION_DONE → LOGGED_IN
"""

import logging
import os

from ..models import WaBotSession
from .validators import (
    validate_fullname,
    validate_email,
    validate_mobile,
    validate_state_selection,
    validate_pincode,
    validate_experience_selection,
    validate_segments_selection,
    format_segments_display,
    format_states_list,
    format_experience_list,
    format_segments_list,
)
from .registration_handler import create_agent_from_wa_data
from .post_login_handler import process_post_login_message
from .payment_service import (
    format_plan_selection_message,
    create_plan_payment_link,
    format_payment_prompt_message,
    activate_agent_subscription_after_payment,
)

logger = logging.getLogger(__name__)


# ── Welcome / registration trigger keywords ─────────────────────────────
REGISTER_KEYWORDS = {'register', 'start', 'signup', 'sign up', 'join', 'hi', 'hello', 'hey', 'namaste'}
CANCEL_KEYWORDS = {'cancel', 'stop', 'exit', 'quit', 'bye'}
RESTART_KEYWORDS = {'restart', 'reset', 'start over', 'new'}


def _build_welcome_message():
    """Build the initial welcome message."""
    return (
        "🙏 *Welcome to Padosi Agent!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "I'm your registration assistant. I'll help you set up your agent account in just a few steps.\n\n"
        "To get started, type *register* or *start*.\n\n"
        "_Already registered? Type your command (e.g., *help*) to continue._"
    )


def _build_ask_fullname_message():
    """Message prompting for full name."""
    return (
        "👤 *Step 1 of 7 — Full Name*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your *full name* as you'd like it to appear on your profile.\n\n"
        "_Example: Rajesh Kumar Patel_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* at any time to stop._"
    )


def _build_ask_email_message():
    """Message prompting for email."""
    return (
        "📧 *Step 2 of 7 — Email Address*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your *email address*.\n"
        "This will be your login ID.\n\n"
        "_Example: rajesh@gmail.com_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_ask_mobile_message():
    """Message prompting for mobile number."""
    return (
        "📱 *Step 3 of 7 — Mobile Number*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your *10-digit mobile number*.\n\n"
        "_Example: 9876543210_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_ask_state_message():
    """Message prompting for state selection."""
    states_list = format_states_list()
    return (
        "📍 *Step 4 of 7 — Select Your State*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Enter the *number* of your state:\n\n"
        f"{states_list}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_ask_pincode_message():
    """Message prompting for pincode."""
    return (
        "📮 *Step 5 of 7 — Area Pincode*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please enter your *6-digit area pincode*.\n\n"
        "_Example: 380015_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_ask_experience_message():
    """Message prompting for experience range."""
    exp_list = format_experience_list()
    return (
        "💼 *Step 6 of 7 — Experience*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select your *experience range*:\n\n"
        f"{exp_list}\n\n"
        "Enter the *number* of your choice.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_ask_segments_message():
    """Message prompting for insurance segments."""
    seg_list = format_segments_list()
    return (
        "🏥 *Step 7 of 7 — Insurance Segments*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select your insurance segments.\n"
        "You can choose *multiple* — separate with commas.\n\n"
        f"{seg_list}\n\n"
        "_Example: 1, 2 (for Health and Life)_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *cancel* to stop or *back* to go to the previous step._"
    )


def _build_confirm_message(reg_data):
    """Build the confirmation summary message."""
    segments_display = format_segments_display(reg_data.get('segments', []))
    return (
        "✅ *Registration Summary*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 *Name:* {reg_data.get('fullname', '')}\n"
        f"📧 *Email:* {reg_data.get('email', '')}\n"
        f"📱 *Mobile:* {reg_data.get('mobile', '')}\n"
        f"📍 *State:* {reg_data.get('state', '')}\n"
        f"📮 *Pincode:* {reg_data.get('agent_pincode', '')}\n"
        f"💼 *Experience:* {reg_data.get('experience_range', '')}\n"
        f"🏥 *Segments:* {segments_display}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Is everything correct?\n\n"
        "✅ Type *yes* to confirm and create your account\n"
        "✏️ Type *edit* to start over\n"
        "❌ Type *cancel* to abort registration"
    )


def _build_credentials_message(email, password, login_url):
    """Build the credentials delivery message."""
    return (
        "🎉 *Account Created Successfully!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Here are your login credentials:\n\n"
        f"🔗 *Login URL:* {login_url}\n"
        f"📧 *Login ID:* {email}\n"
        f"🔑 *Password:* `{password}`\n\n"
        "⚠️ *Important:*\n"
        "• Please save these credentials securely\n"
        "• Change your password after first login\n"
        "• Do not share your password with anyone\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "You can now use the following commands:\n"
        "Type *help* to see all available commands."
    )


def _build_cancel_message():
    """Message when registration is cancelled."""
    return (
        "❌ *Registration Cancelled*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your registration has been cancelled. No data has been saved.\n\n"
        "To start again, type *register* or *start* anytime.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


def _build_already_registered_message(email, login_url):
    """Message for already registered agents."""
    return (
        "ℹ️ *Already Registered!*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"You're already registered with email: *{email}*\n\n"
        f"🔗 *Login URL:* {login_url}\n\n"
        "Type *help* to see available commands.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━"
    )


BACK_STATE_MAP = {
    WaBotSession.STATE_ASK_EMAIL: WaBotSession.STATE_ASK_FULLNAME,
    WaBotSession.STATE_ASK_MOBILE: WaBotSession.STATE_ASK_EMAIL,
    WaBotSession.STATE_ASK_STATE: WaBotSession.STATE_ASK_MOBILE,
    WaBotSession.STATE_ASK_PINCODE: WaBotSession.STATE_ASK_STATE,
    WaBotSession.STATE_ASK_EXPERIENCE: WaBotSession.STATE_ASK_PINCODE,
    WaBotSession.STATE_ASK_SEGMENTS: WaBotSession.STATE_ASK_EXPERIENCE,
    WaBotSession.STATE_CONFIRM_DETAILS: WaBotSession.STATE_ASK_SEGMENTS,
    WaBotSession.STATE_ASK_PLAN: WaBotSession.STATE_CONFIRM_DETAILS,
    WaBotSession.STATE_AWAITING_PAYMENT: WaBotSession.STATE_ASK_PLAN,
}

# ── Prompt builders per state ───────────────────────────────────────────
STATE_PROMPTS = {
    WaBotSession.STATE_ASK_FULLNAME: _build_ask_fullname_message,
    WaBotSession.STATE_ASK_EMAIL: _build_ask_email_message,
    WaBotSession.STATE_ASK_MOBILE: _build_ask_mobile_message,
    WaBotSession.STATE_ASK_STATE: _build_ask_state_message,
    WaBotSession.STATE_ASK_PINCODE: _build_ask_pincode_message,
    WaBotSession.STATE_ASK_EXPERIENCE: _build_ask_experience_message,
    WaBotSession.STATE_ASK_SEGMENTS: _build_ask_segments_message,
    WaBotSession.STATE_ASK_PLAN: format_plan_selection_message,
}


def process_message(session, user_text):
    """
    Main entry point: process an incoming message based on the session's
    current state and return the reply text.

    Args:
        session: WaBotSession instance
        user_text: Incoming message text

    Returns:
        str: Reply message text to send back
    """
    text = user_text.strip()
    text_lower = text.lower()
    current_state = session.state

    # ── Global: handle cancel at any registration state ─────────────
    if current_state not in (WaBotSession.STATE_WELCOME, WaBotSession.STATE_LOGGED_IN):
        if text_lower in CANCEL_KEYWORDS:
            session.state = WaBotSession.STATE_WELCOME
            session.registration_data = {}
            session.save()
            return _build_cancel_message()

    # ── Global: handle "back" during registration ───────────────────
    if current_state in BACK_STATE_MAP and text_lower == 'back':
        prev_state = BACK_STATE_MAP[current_state]
        session.state = prev_state
        session.save()
        prompt_fn = STATE_PROMPTS.get(prev_state)
        if prompt_fn:
            return prompt_fn()
        return _build_welcome_message()

    # ── Global: handle restart ──────────────────────────────────────
    if text_lower in RESTART_KEYWORDS and current_state != WaBotSession.STATE_LOGGED_IN:
        session.state = WaBotSession.STATE_WELCOME
        session.registration_data = {}
        session.save()
        return _build_welcome_message()

    # ── Route to state-specific handler ─────────────────────────────
    if current_state == WaBotSession.STATE_WELCOME:
        return _handle_welcome(session, text, text_lower)
    elif current_state == WaBotSession.STATE_ASK_FULLNAME:
        return _handle_ask_fullname(session, text)
    elif current_state == WaBotSession.STATE_ASK_EMAIL:
        return _handle_ask_email(session, text)
    elif current_state == WaBotSession.STATE_ASK_MOBILE:
        return _handle_ask_mobile(session, text)
    elif current_state == WaBotSession.STATE_ASK_STATE:
        return _handle_ask_state(session, text)
    elif current_state == WaBotSession.STATE_ASK_PINCODE:
        return _handle_ask_pincode(session, text)
    elif current_state == WaBotSession.STATE_ASK_EXPERIENCE:
        return _handle_ask_experience(session, text)
    elif current_state == WaBotSession.STATE_ASK_SEGMENTS:
        return _handle_ask_segments(session, text)
    elif current_state == WaBotSession.STATE_CONFIRM_DETAILS:
        return _handle_confirm(session, text, text_lower)
    elif current_state == WaBotSession.STATE_ASK_PLAN:
        return _handle_ask_plan(session, text, text_lower)
    elif current_state == WaBotSession.STATE_AWAITING_PAYMENT:
        return _handle_awaiting_payment(session, text, text_lower)
    elif current_state == WaBotSession.STATE_LOGGED_IN:
        return _handle_logged_in(session, text)
    else:
        # Unknown state — reset to welcome
        logger.warning(f"[WA-Bot] Unknown state '{current_state}' for {session.phone_number}, resetting")
        session.state = WaBotSession.STATE_WELCOME
        session.registration_data = {}
        session.save()
        return _build_welcome_message()


# ── State handlers ──────────────────────────────────────────────────────

def _handle_welcome(session, text, text_lower):
    """Handle messages in WELCOME state."""
    # Check if already registered
    if session.is_registered and session.agent:
        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        login_url = f"{site_url}/agent-login/"

        # If they say register again, tell them they're already registered
        if text_lower in REGISTER_KEYWORDS:
            session.state = WaBotSession.STATE_LOGGED_IN
            session.is_logged_in = True
            session.save()
            return _build_already_registered_message(session.agent.email, login_url)

        # Route to post-login handler
        session.state = WaBotSession.STATE_LOGGED_IN
        session.is_logged_in = True
        session.save()
        return process_post_login_message(session.agent, text)

    # New user — check for registration keywords
    if text_lower in REGISTER_KEYWORDS:
        session.state = WaBotSession.STATE_ASK_FULLNAME
        session.registration_data = {}
        session.save()
        return _build_ask_fullname_message()

    # Unknown message from unregistered user
    return _build_welcome_message()


def _handle_ask_fullname(session, text):
    """Handle name input."""
    is_valid, result = validate_fullname(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_fullname_message()

    reg_data = session.registration_data or {}
    reg_data['fullname'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_EMAIL
    session.save()
    return _build_ask_email_message()


def _handle_ask_email(session, text):
    """Handle email input with uniqueness check."""
    from apps.agents.models import Agent

    is_valid, result = validate_email(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_email_message()

    # Check uniqueness
    if Agent.objects.filter(email=result).exists():
        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        return (
            f"⚠️ An account with email *{result}* already exists.\n\n"
            f"If this is your account, please login at:\n🔗 {site_url}/agent-login/\n\n"
            "Otherwise, please enter a *different email address*:"
        )

    reg_data = session.registration_data or {}
    reg_data['email'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_MOBILE
    session.save()
    return _build_ask_mobile_message()


def _handle_ask_mobile(session, text):
    """Handle mobile number input with uniqueness check."""
    from apps.agents.models import Agent

    is_valid, result = validate_mobile(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_mobile_message()

    # Check uniqueness
    if Agent.objects.filter(mobile=result).exists():
        return (
            f"⚠️ An account with mobile *{result}* already exists.\n\n"
            "Please enter a *different mobile number*:"
        )

    reg_data = session.registration_data or {}
    reg_data['mobile'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_STATE
    session.save()
    return _build_ask_state_message()


def _handle_ask_state(session, text):
    """Handle state selection."""
    is_valid, result = validate_state_selection(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_state_message()

    reg_data = session.registration_data or {}
    reg_data['state'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_PINCODE
    session.save()
    return _build_ask_pincode_message()


def _handle_ask_pincode(session, text):
    """Handle pincode input."""
    is_valid, result = validate_pincode(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_pincode_message()

    reg_data = session.registration_data or {}
    reg_data['agent_pincode'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_EXPERIENCE
    session.save()
    return _build_ask_experience_message()


def _handle_ask_experience(session, text):
    """Handle experience range selection."""
    is_valid, result = validate_experience_selection(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_experience_message()

    reg_data = session.registration_data or {}
    reg_data['experience_range'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_ASK_SEGMENTS
    session.save()
    return _build_ask_segments_message()


def _handle_ask_segments(session, text):
    """Handle insurance segments selection."""
    is_valid, result = validate_segments_selection(text)
    if not is_valid:
        return f"❌ {result}\n\n" + _build_ask_segments_message()

    reg_data = session.registration_data or {}
    reg_data['segments'] = result
    session.registration_data = reg_data
    session.state = WaBotSession.STATE_CONFIRM_DETAILS
    session.save()
    return _build_confirm_message(reg_data)


def _handle_confirm(session, text, text_lower):
    """Handle confirmation of registration details."""
    if text_lower in ('yes', 'y', 'confirm', 'ok', 'done', 'ha', 'haa'):
        # ── Advance to Plan Selection ───────────────────────────────
        session.state = WaBotSession.STATE_ASK_PLAN
        session.save()
        return "✅ *Details Confirmed!*\n\n" + format_plan_selection_message()

    elif text_lower in ('edit', 'change', 'modify', 'badlo'):
        session.state = WaBotSession.STATE_ASK_FULLNAME
        session.registration_data = {}
        session.save()
        return (
            "✏️ Let's start over.\n\n"
            + _build_ask_fullname_message()
        )

    elif text_lower in CANCEL_KEYWORDS:
        session.state = WaBotSession.STATE_WELCOME
        session.registration_data = {}
        session.save()
        return _build_cancel_message()

    else:
        return (
            "Please reply with:\n\n"
            "✅ *yes* — to confirm and choose your plan\n"
            "✏️ *edit* — to change your details\n"
            "❌ *cancel* — to abort registration"
        )


def _handle_ask_plan(session, text, text_lower):
    """Handle plan selection (1: Starter, 2: Professional, 3: Trial)."""
    plan_key = None

    if text_lower in ('1', 'starter', 'starter plan'):
        plan_key = 'starter'
    elif text_lower in ('2', 'professional', 'pro', 'professional plan'):
        plan_key = 'professional'
    elif text_lower in ('3', 'trial', 'free trial', 'free_trial', 'trial plan'):
        plan_key = 'free_trial'
    elif text_lower in ('edit', 'change'):
        session.state = WaBotSession.STATE_ASK_FULLNAME
        session.registration_data = {}
        session.save()
        return "✏️ Let's start over.\n\n" + _build_ask_fullname_message()

    if not plan_key:
        return (
            "❌ Invalid option. Please select your plan by replying with:\n\n"
            "1️⃣ *1* — Starter Plan (₹1,769/yr)\n"
            "2️⃣ *2* — Professional Plan (₹9,439/yr)\n"
            "3️⃣ *3* — 30-Day Trial Plan\n\n"
            "_(Or reply *back* to review your details)_"
        )

    # Generate payment link and save pending agent
    payment_info = create_plan_payment_link(session, plan_key)

    # If trial is completely free (₹0), activate immediately
    if plan_key == 'free_trial' and payment_info['total'] == 0:
        activate_agent_subscription_after_payment(payment_info['subscription'].id)
        session.state = WaBotSession.STATE_LOGGED_IN
        session.is_registered = True
        session.is_logged_in = True
        session.save()
        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        return _build_credentials_message(
            payment_info['agent'].email,
            session.registration_data.get('temp_password', ''),
            f"{site_url}/agent-login/",
        )

    # Move to awaiting payment
    session.state = WaBotSession.STATE_AWAITING_PAYMENT
    session.save()

    return format_payment_prompt_message(payment_info)


def _handle_awaiting_payment(session, text, text_lower):
    """Handle messages while waiting for payment completion."""
    # Allow switching plans
    if text_lower in ('change', 'change plan', 'plan', 'switch'):
        session.state = WaBotSession.STATE_ASK_PLAN
        session.save()
        return format_plan_selection_message()

    # Check if payment was completed in background (e.g. via webhook)
    reg_data = session.registration_data or {}
    sub_id = reg_data.get('subscription_id')
    if sub_id:
        try:
            from apps.agents.models import AgentSubscription
            sub = AgentSubscription.objects.filter(pk=sub_id, payment_status='completed').first()
            if sub:
                session.state = WaBotSession.STATE_LOGGED_IN
                session.is_registered = True
                session.is_logged_in = True
                session.save()
                return process_post_login_message(session.agent, text)
        except Exception:
            pass

    payment_link = reg_data.get('payment_link', '')
    plan_name = reg_data.get('plan_name', 'Membership Plan')
    total = reg_data.get('plan_total', '')

    return (
        f"⏳ *Payment is Pending for {plan_name}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Amount: ₹{total}\n\n"
        f"👉 *Complete payment securely here:*\n"
        f"{payment_link}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Once payment is completed, your account will be activated instantly!\n\n"
        f"_Type *change* to select a different plan or *cancel* to abort._"
    )


def _handle_logged_in(session, text):
    """Handle messages from logged-in/registered agents."""
    if not session.agent:
        # Edge case: session says logged in but no agent linked
        session.state = WaBotSession.STATE_WELCOME
        session.is_registered = False
        session.is_logged_in = False
        session.save()
        return _build_welcome_message()

    return process_post_login_message(session.agent, text)
