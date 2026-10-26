"""
WhatsApp Agent Bot — Post-Login Handler

Handles all commands AFTER an agent is registered and logged in.
Enforces strict boundaries — only recognized commands are processed.
Anything outside scope gets a polite rejection.

Supported commands:
  help / menu     → Show available commands
  profile         → View profile summary
  dashboard       → Get dashboard link
  referral        → Get referral code/link
  status          → Check account status
  support         → Contact support info
"""

import logging
import os

from apps.wa_agent_bot.services.site_url import bot_site_url

logger = logging.getLogger(__name__)


# ── Command definitions ─────────────────────────────────────────────────
COMMANDS = {
    'help': ['help', 'menu', 'commands', 'options', '?'],
    'profile': ['profile', 'my profile', 'myprofile', 'view profile'],
    'dashboard': ['dashboard', 'my dashboard', 'mydashboard', 'panel'],
    'card': ['card', 'my card', 'visiting card', 'digital card', 'visiting'],
    'referral': ['referral', 'refer', 'referral code', 'share', 'invite'],
    'status': ['status', 'my status', 'account status', 'plan', 'subscription'],
    'support': ['support', 'help support', 'contact', 'customer support', 'issue', 'problem'],
    'credentials': ['password', 'mypassword', 'my password', 'login', 'id', 'user id', 'credentials', 'pass'],
}


def _match_command(user_text):
    """
    Match user input to a known command.
    Returns the command key or None if no match.
    """
    cleaned = user_text.strip().lower()

    # Exact match first
    for cmd_key, aliases in COMMANDS.items():
        for alias in aliases:
            if cleaned == alias:
                return cmd_key

    # Partial match (starts with)
    for cmd_key, aliases in COMMANDS.items():
        for alias in aliases:
            if cleaned.startswith(alias) or alias.startswith(cleaned):
                return cmd_key

    return None


def handle_help():
    """Show the help menu with available commands."""
    return (
        "📋 *Available Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 *profile* — View your profile summary\n"
        "📇 *card* — View your digital visiting card link\n"
        "📊 *dashboard* — Get your dashboard link\n"
        "🔑 *password* — View your login credentials\n"
        "🔗 *referral* — Get your referral code & link\n"
        "📈 *status* — Check your account & approval status\n"
        "🆘 *support* — Get support contact info\n"
        "❓ *help* — Show this menu\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Just type any command to get started!_"
    )


def handle_card(agent):
    """Provide visiting card link and public status."""
    site_url = bot_site_url()
    slug = None
    try:
        profile = agent.get_primary_profile()
        if profile and profile.slug:
            slug = profile.slug
    except Exception:
        pass

    if not slug:
        slug = str(agent.id)

    card_url = f"{site_url}/card/{slug}/"
    if agent.status == 'pending_approval':
        status_line = "⏳ _Status: Pending Admin Approval. Your card will become publicly visible once approved by our team._"
    elif agent.status == 'active':
        status_line = "✅ _Status: Active & Live! Tap the link above to view and share with clients._"
    else:
        status_line = f"⚠️ _Status: {agent.status.title()}._"

    return (
        "📇 *Your Digital Visiting Card*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 {card_url}\n\n"
        f"{status_line}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_profile(agent):
    """Show the agent's profile summary."""
    from apps.agents.services.feature_unlock import paid_plan_label

    plan_display = paid_plan_label(agent.plan_type) if agent.plan_type else 'None'
    segments = ', '.join(agent.user_types) if agent.user_types else 'None'

    site_url = bot_site_url()

    # Try to get the profile slug
    profile_url = ''
    try:
        profile = agent.get_primary_profile()
        if profile and profile.slug:
            if agent.status == 'active':
                profile_url = f"\n🔗 *Profile URL:* {site_url}/profile/{profile.slug}/"
            else:
                profile_url = f"\n🔗 *Profile URL:* {site_url}/profile/{profile.slug}/ _(Live after admin approval)_"
    except Exception:
        pass

    status_tag = agent.status.title()
    if agent.status == 'pending_approval':
        status_tag = "⏳ Pending Approval (Under Review)"
    elif agent.status == 'active':
        status_tag = "✅ Active & Verified"

    return (
        "👤 *Your Profile*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 *Name:* {agent.fullname}\n"
        f"📧 *Email:* {agent.email}\n"
        f"📱 *Mobile:* {agent.mobile}\n"
        f"📍 *Pincode:* {agent.agent_pincode or 'Not set'}\n"
        f"💼 *Experience:* {agent.experience_range or 'Not set'}\n"
        f"🏥 *Segments:* {segments}\n"
        f"⭐ *Plan:* {plan_display}\n"
        f"📌 *Status:* {status_tag}"
        f"{profile_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_dashboard(agent):
    """Provide the dashboard link."""
    site_url = bot_site_url()
    dashboard_url = f"{site_url}/agent/dashboard/"

    return (
        "📊 *Your Dashboard*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click the link below to access your dashboard:\n\n"
        f"🔗 {dashboard_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Log in with your email & mobile number as password._"
    )


def handle_referral(agent):
    """Provide referral code and link."""
    site_url = bot_site_url()

    # Try to get referral code from the agent's profile or generate from ID
    referral_code = ''
    try:
        profile = agent.get_primary_profile()
        if profile and hasattr(profile, 'referral_code') and profile.referral_code:
            referral_code = profile.referral_code
    except Exception:
        pass

    if not referral_code:
        referral_code = f"PA{agent.id:06d}"

    referral_link = f"{site_url}/join/{referral_code}/"

    return (
        "🔗 *Your Referral Info*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📋 *Referral Code:* `{referral_code}`\n"
        f"🔗 *Referral Link:* {referral_link}\n\n"
        "Share this link with other agents to earn rewards!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_status(agent):
    """Check account and subscription status."""
    from apps.agents.services.feature_unlock import paid_plan_label
    from django.utils import timezone

    plan_display = paid_plan_label(agent.plan_type) if agent.plan_type else 'None'

    # Check subscription
    sub_info = "No active subscription"
    try:
        sub = agent.activeSubscription
        if sub:
            days_left = (sub.expires_at - timezone.now()).days
            sub_info = f"Paid & Verified (expires in {days_left} days)"
    except Exception:
        pass

    # Check trial
    trial_info = ""
    if agent.plan_type == 'free_trial':
        if agent.isOnFreeTrial():
            days_left = (agent.trial_ends_at - timezone.now()).days
            trial_info = f"\n⏰ *Trial:* {days_left} days remaining"
        elif agent.isTrialExpired():
            trial_info = "\n⏰ *Trial:* Expired"

    if agent.status == 'pending_approval':
        status_display = "⏳ Pending Admin Approval (Under Review)"
        status_note = "\n\nℹ️ *Note:* Your payment is confirmed and your registration is currently being reviewed by the admin team. Once approved, your digital card and public profile will go LIVE!"
    elif agent.status == 'active':
        status_display = "✅ Active & Verified"
        status_note = "\n\n✨ Your account is fully approved and your public profile is LIVE!"
    elif agent.status == 'suspended':
        status_display = "⚠️ Suspended"
        status_note = "\n\n⚠️ Your account is temporarily suspended. Please contact support."
    elif agent.status == 'rejected':
        status_display = "❌ Rejected"
        status_note = "\n\n❌ Your application was not approved. Please contact support."
    else:
        status_display = agent.status.title()
        status_note = ""

    return (
        "📈 *Account Status*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 *Name:* {agent.fullname}\n"
        f"⭐ *Plan:* {plan_display}\n"
        f"📋 *Payment & Subscription:* {sub_info}"
        f"{trial_info}\n"
        f"📌 *Approval Status:* {status_display}\n"
        f"⭐ *Rating:* {agent.average_rating:.1f}/5 ({agent.review_count} reviews)"
        f"{status_note}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_support():
    """Provide support contact information."""
    return (
        "🆘 *Support*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Need help? Contact our support team:\n\n"
        "📧 *Email:* support@padosiagent.com\n"
        "🌐 *Website:* www.padosiagent.com\n\n"
        "Our team will respond within 24 hours.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_credentials(agent):
    """Provide the agent's login information and password reminder."""
    site_url = bot_site_url()
    login_url = f"{site_url}/agent-login/"
    reset_url = f"{site_url}/password-reset/"
    mobile_clean = ''.join(c for c in (agent.mobile or '') if c.isdigit())
    pw = mobile_clean[-10:] if len(mobile_clean) >= 10 else (mobile_clean or 'Your registered phone number')

    return (
        "🔑 *Your Login Credentials*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🌐 *Login URL:* {login_url}\n"
        f"📧 *Email / User ID:* {agent.email}\n"
        f"🔒 *Password:* `{pw}`\n"
        f"_(Your default password is your 10-digit registered mobile number)_\n\n"
        f"Forgot or want to change your password?\n"
        f"👉 Reset here: {reset_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_boundary_message():
    """
    Polite rejection for any message that is outside the supported commands.
    This is the STRICT BOUNDARY enforcement.
    """
    return (
        "🙏 I appreciate your message, but I can only help you with specific commands.\n\n"
        "Type *help* to see the list of available commands.\n\n"
        "_I'm here to assist you with your profile, dashboard, referral, status, login credentials, and support queries only._"
    )


def process_post_login_message(agent, user_text):
    """
    Process a message from a logged-in agent.

    Args:
        agent: Agent model instance
        user_text: The incoming message text

    Returns:
        str: Reply message text
    """
    command = _match_command(user_text)

    if command == 'help':
        return handle_help()
    elif command == 'profile':
        return handle_profile(agent)
    elif command == 'card':
        return handle_card(agent)
    elif command == 'dashboard':
        return handle_dashboard(agent)
    elif command == 'referral':
        return handle_referral(agent)
    elif command == 'status':
        return handle_status(agent)
    elif command == 'support':
        return handle_support()
    elif command == 'credentials':
        return handle_credentials(agent)
    else:
        # ── STRICT BOUNDARY ─────────────────────────────────────────
        return handle_boundary_message()
