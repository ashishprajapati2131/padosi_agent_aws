"""
Admin-editable WhatsApp texts: notification templates and keyword auto-replies.

Both live in SiteSetting (one JSON value each), so reading them per message is a cache hit.
"""
import logging
import re

logger = logging.getLogger(__name__)

TEMPLATES_SETTING = 'wa_message_templates'
KEYWORDS_SETTING = 'wa_keyword_replies'
MAX_TEMPLATE_LEN = 3000
MAX_KEYWORDS = 100

# key -> label, placeholders admins may use, default text (used when not overridden or when an edit is broken)
TEMPLATES = {
    'lead_alert': {
        'label': 'New lead alert (to agent)',
        'placeholders': ['agent_name', 'customer_name', 'customer_mobile', 'customer_email',
                         'interested_in', 'pincode', 'requirement', 'dashboard_url'],
        'default': (
            "🔔 *New Lead on PadosiAgent!*\n\n"
            "👤 *Name:* {customer_name}\n"
            "📱 *Mobile:* {customer_mobile}\n"
            "📧 *Email:* {customer_email}\n"
            "🛡️ *Interested in:* {interested_in}\n"
            "📍 *Pincode:* {pincode}\n"
            "📝 *Requirement:* {requirement}\n\n"
            "👉 View all leads: {dashboard_url}\n"
            "_Please contact the customer soon._"
        ),
    },
    'card_view_alert': {
        'label': 'Card shown in a pincode search (to agent, max once a day)',
        'placeholders': ['agent_name', 'pincode', 'dashboard_url'],
        'default': (
            "👀 *Hi {agent_name}!*\n\n"
            "A client searched for agents in pincode *{pincode}* and your card was shown to them on PadosiAgent.\n\n"
            "👉 See your views and leads: {dashboard_url}"
        ),
    },
    'profile_view_alert': {
        'label': 'Profile viewed by a client (to agent, max once a day)',
        'placeholders': ['agent_name', 'dashboard_url'],
        'default': (
            "👀 *Hi {agent_name}!*\n\n"
            "A client just viewed your profile on PadosiAgent.\n\n"
            "👉 See your views and leads: {dashboard_url}"
        ),
    },
    'approval': {
        'label': 'Account approved (to agent)',
        'placeholders': ['agent_name', 'profile_url', 'card_url', 'dashboard_url'],
        'default': (
            "🎉 *Congratulations, {agent_name}!* 🌟\n\n"
            "Great news! Your PadosiAgent account has been *APPROVED* by our admin team! 🚀\n"
            "Your public profile and digital visiting card are now *LIVE* and visible to clients.\n\n"
            "🌐 *Public Profile Link:*\n{profile_url}\n\n"
            "📇 *Digital Visiting Card:*\n{card_url}\n\n"
            "📊 *Agent Dashboard:*\n{dashboard_url}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *Next Steps:*\n"
            "1. Share your Digital Visiting Card with clients on WhatsApp & Social Media\n"
            "2. Log in to your dashboard to view customer leads and reviews\n\n"
            "💬 *WhatsApp Agent Assistant is Ready!*\n"
            "Type *card* to view your visiting card link, or *help* for all commands."
        ),
    },
    'rejection': {
        'label': 'Account not approved (to agent)',
        'placeholders': ['agent_name', 'reason'],
        'default': (
            "Dear {agent_name},\n\n"
            "Your application on PadosiAgent has been reviewed by the admin team.\n"
            "*Reason:* {reason}\n\n"
            "Status: *Not Approved / Action Required*\n\n"
            "Please reach out to our support team at support@padosiagent.com if you believe this is "
            "an error or need assistance updating your documents."
        ),
    },
    'welcome': {
        'label': 'Payment received + login details (to agent)',
        'placeholders': ['agent_name', 'login_url', 'email', 'password', 'plan'],
        'default': (
            "🎉 *Payment Received, {agent_name}!* 🚀\n"
            "Your payment was successfully verified and your registration is submitted for *Admin Approval*.\n\n"
            "⏳ *Account Status:* Pending Admin Approval\n"
            "Our admin team will review your application shortly. Once approved, your public profile and "
            "digital visiting card will go *LIVE*!\n\n"
            "🔑 *Your Portal Login Credentials:*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "🌐 *Login URL:* {login_url}\n"
            "📧 *Email / User ID:* {email}\n"
            "🔒 *Password:* `{password}` _(Your registered mobile number)_\n"
            "📦 *Selected Plan:* {plan}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *What you can do now:*\n"
            "1. Login to your dashboard using your mobile number as password\n"
            "2. Review your personal profile and business details\n"
            "3. You will receive an instant WhatsApp alert here as soon as the admin approves your account!\n\n"
            "💬 *WhatsApp Agent Assistant is Ready!*\n"
            "Type *status* anytime to check your approval status, or *help* to see all commands."
        ),
    },
}

# Anything inside braces, so {name.attr} / {name:fmt} are rejected rather than formatted.
_PLACEHOLDER_RE = re.compile(r'{([^{}]*)}')


def _setting(key, default):
    from apps.home.models.site_setting import SiteSetting
    try:
        val = SiteSetting.get_value(key, default)
    except Exception as e:  # settings unreadable: still send, with the built-in texts
        logger.error(f"[WA-Templates] Could not read {key}: {e}")
        return default
    return val if isinstance(val, type(default)) else default


def get_overrides():
    return _setting(TEMPLATES_SETTING, {})


def template_errors(key, text):
    """Return a list of problems with an admin-edited template ([] when it is safe to save)."""
    errors = []
    if len(text) > MAX_TEMPLATE_LEN:
        errors.append(f'Message is longer than {MAX_TEMPLATE_LEN} characters.')
    unknown = sorted({p for p in _PLACEHOLDER_RE.findall(text)} - set(TEMPLATES[key]['placeholders']))
    if unknown:
        errors.append('Unknown placeholder(s): ' + ', '.join('{' + p + '}' for p in unknown))
    try:
        text.format_map({p: '' for p in TEMPLATES[key]['placeholders']})
    except (ValueError, IndexError, KeyError, AttributeError) as e:
        errors.append(f'Invalid braces: {e}. Use only {{placeholder}} names listed below.')
    return errors


def _fill(text, values):
    unknown = set(_PLACEHOLDER_RE.findall(text)) - set(values)
    if unknown:
        raise KeyError(', '.join(sorted(unknown)))
    # A line whose placeholder has no value (e.g. no email given) is left out instead of showing a blank.
    empty = {k for k, v in values.items() if not v}
    kept = [line for line in text.splitlines() if not (set(_PLACEHOLDER_RE.findall(line)) & empty)]
    return '\n'.join(kept).format_map(values)


def render(key, **context):
    """Fill a template with context. Falls back to the default text if an admin edit is broken."""
    spec = TEMPLATES[key]
    values = {p: ('' if context.get(p) is None else str(context.get(p)).strip()) for p in spec['placeholders']}
    text = get_overrides().get(key) or spec['default']
    try:
        return _fill(text, values)
    except (ValueError, IndexError, KeyError, AttributeError) as e:
        logger.error(f"[WA-Templates] Broken template '{key}', using default: {e}")
        return _fill(spec['default'], values)


def get_keyword_replies():
    return _setting(KEYWORDS_SETTING, [])


def match_keyword_reply(text):
    """Admin auto-reply for an incoming message, or None. 'exact' compares the whole message, 'contains' any part."""
    msg = (text or '').strip().lower()
    if not msg:
        return None
    for rule in get_keyword_replies():
        if not rule.get('active', True):
            continue
        keyword = (rule.get('keyword') or '').strip().lower()
        if keyword and (msg == keyword if rule.get('match') != 'contains' else keyword in msg):
            return rule.get('reply') or None
    return None
