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

logger = logging.getLogger(__name__)


# ── Command definitions ─────────────────────────────────────────────────
COMMANDS = {
    'help': ['help', 'menu', 'commands', 'options', '?'],
    'profile': ['profile', 'my profile', 'myprofile', 'view profile'],
    'dashboard': ['dashboard', 'my dashboard', 'mydashboard', 'panel'],
    'referral': ['referral', 'refer', 'referral code', 'share', 'invite'],
    'status': ['status', 'my status', 'account status', 'plan', 'subscription'],
    'support': ['support', 'help support', 'contact', 'customer support', 'issue', 'problem'],
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
        "📊 *dashboard* — Get your dashboard link\n"
        "🔗 *referral* — Get your referral code & link\n"
        "📈 *status* — Check your account & plan status\n"
        "🆘 *support* — Get support contact info\n"
        "❓ *help* — Show this menu\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Just type any command to get started!_"
    )


def handle_profile(agent):
    """Show the agent's profile summary."""
    from apps.agents.services.feature_unlock import paid_plan_label

    plan_display = paid_plan_label(agent.plan_type) if agent.plan_type else 'None'
    segments = ', '.join(agent.user_types) if agent.user_types else 'None'

    site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')

    # Try to get the profile slug
    profile_url = ''
    try:
        profile = agent.get_primary_profile()
        if profile and profile.slug:
            profile_url = f"\n🔗 *Profile URL:* {site_url}/profile/{profile.slug}/"
    except Exception:
        pass

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
        f"✅ *Status:* {agent.status.title()}"
        f"{profile_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Type *help* to see all commands._"
    )


def handle_dashboard(agent):
    """Provide the dashboard link."""
    site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
    dashboard_url = f"{site_url}/agent/dashboard/"

    return (
        "📊 *Your Dashboard*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click the link below to access your dashboard:\n\n"
        f"🔗 {dashboard_url}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "_Log in with your email & password to access._"
    )


def handle_referral(agent):
    """Provide referral code and link."""
    site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')

    # Try to get referral code from the agent's profile or generate from ID
    referral_code = ''
    try:
        profile = agent.get_primary_profile()
        if profile and hasattr(profile, 'referral_code') and profile.referral_code:
            referral_code = profile.referral_code
    except Exception:
        pass

    if not referral_code:
        # Fallback: use agent ID as a basic code
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
            sub_info = f"Active (expires in {days_left} days)"
    except Exception:
        pass

    # Check trial
    trial_info = ""
    if agent.plan_type == 'free_trial':
        if agent.isOnFreeTrial():
            from django.utils import timezone
            days_left = (agent.trial_ends_at - timezone.now()).days
            trial_info = f"\n⏰ *Trial:* {days_left} days remaining"
        elif agent.isTrialExpired():
            trial_info = "\n⏰ *Trial:* Expired"

    return (
        "📈 *Account Status*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 *Name:* {agent.fullname}\n"
        f"⭐ *Plan:* {plan_display}\n"
        f"📋 *Subscription:* {sub_info}"
        f"{trial_info}\n"
        f"✅ *Account Status:* {agent.status.title()}\n"
        f"⭐ *Rating:* {agent.average_rating:.1f}/5 ({agent.review_count} reviews)\n\n"
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


def handle_boundary_message():
    """
    Polite rejection for any message that is outside the supported commands.
    This is the STRICT BOUNDARY enforcement.
    """
    return (
        "🙏 I appreciate your message, but I can only help you with specific commands.\n\n"
        "Type *help* to see the list of available commands.\n\n"
        "_I'm here to assist you with your profile, dashboard, referral, status, and support queries only._"
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
    elif command == 'dashboard':
        return handle_dashboard(agent)
    elif command == 'referral':
        return handle_referral(agent)
    elif command == 'status':
        return handle_status(agent)
    elif command == 'support':
        return handle_support()
    else:
        # ── STRICT BOUNDARY ─────────────────────────────────────────
        return handle_boundary_message()
