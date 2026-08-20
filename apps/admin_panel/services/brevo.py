"""
Compatibility wrapper.

Canonical email implementation: apps.agents.services.brevo
Keep this module so existing admin_panel imports continue to work.
"""

from apps.agents.services.brevo import (  # noqa: F401
    BrevoEmailService,
    email_service,
    send_brevo_email,
    send_otp_email,
)
