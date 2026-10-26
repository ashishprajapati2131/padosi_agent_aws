"""
WhatsApp Agent Bot — Registration Handler

Handles the actual creation of an Agent account once all registration
data has been collected and confirmed via the WhatsApp conversation.

Creates:
  - Django User
  - Agent record
  - Generates temporary password
  - Returns login credentials
"""

import logging
import os
import secrets
import string

from django.contrib.auth.models import User
from django.db import IntegrityError

logger = logging.getLogger(__name__)


def _generate_password(length=10):
    """Generate a secure random password with mixed characters."""
    # Ensure at least one of each type
    lowercase = secrets.choice(string.ascii_lowercase)
    uppercase = secrets.choice(string.ascii_uppercase)
    digit = secrets.choice(string.digits)
    special = secrets.choice('!@#$%&*')
    # Fill the rest
    remaining = length - 4
    pool = string.ascii_letters + string.digits + '!@#$%&*'
    rest = ''.join(secrets.choice(pool) for _ in range(remaining))
    # Shuffle all together
    password_chars = list(lowercase + uppercase + digit + special + rest)
    secrets.SystemRandom().shuffle(password_chars)
    return ''.join(password_chars)


def _generate_slug(fullname, email):
    """Generate a URL-friendly slug from the agent's name."""
    import re
    # Start with fullname
    slug = fullname.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = slug.strip('-')

    if not slug:
        # Fallback to email prefix
        slug = email.split('@')[0].lower()
        slug = re.sub(r'[^a-z0-9-]', '', slug)

    return slug


def _ensure_unique_slug(slug, exclude_profile_id=None):
    """Make sure the slug is unique by appending a number if needed."""
    from apps.agents.models import AgentProfile
    from django.utils.text import slugify
    base = slugify(slug) or 'agent'
    candidate = base
    counter = 1
    qs = AgentProfile.objects.all()
    if exclude_profile_id:
        qs = qs.exclude(id=exclude_profile_id)
    while qs.filter(slug=candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1
        if counter > 500:
            candidate = f"{base}-{secrets.token_hex(4)}"
            break
    return candidate


def create_agent_from_wa_data(registration_data):
    """
    Create a new Agent account from the collected WhatsApp registration data.

    Args:
        registration_data: dict with keys:
            - fullname, email, mobile, state, agent_pincode,
              experience_range, segments

    Returns:
        dict with:
            - success (bool)
            - agent (Agent instance, if success)
            - password (str, generated password)
            - login_url (str)
            - error (str, if not success)
    """
    from apps.agents.models import Agent

    email = registration_data.get('email', '').strip().lower()
    fullname = registration_data.get('fullname', '').strip()
    mobile = registration_data.get('mobile', '').strip()
    state = registration_data.get('state', '').strip()
    agent_pincode = registration_data.get('agent_pincode', '').strip()
    experience_range = registration_data.get('experience_range', '').strip()
    segments = registration_data.get('segments', [])

    # ── Pre-flight checks ───────────────────────────────────────────
    if Agent.objects.filter(email=email).exists():
        return {
            'success': False,
            'error': f"An agent with email *{email}* is already registered. Please use a different email or contact support.",
        }

    if Agent.objects.filter(mobile=mobile).exists():
        return {
            'success': False,
            'error': f"An agent with mobile *{mobile}* is already registered. Please use a different number or contact support.",
        }

    # ── Password is agent's 10-digit mobile number ───────────────────
    mobile_digits = ''.join(c for c in mobile if c.isdigit())
    password = mobile_digits[-10:] if len(mobile_digits) >= 10 else mobile_digits
    slug = _generate_slug(fullname, email)

    # ── Create Django User ──────────────────────────────────────────
    try:
        # Use email as username (consistent with existing auth flow)
        username = email
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=fullname.split()[0] if fullname else '',
            last_name=' '.join(fullname.split()[1:]) if len(fullname.split()) > 1 else '',
        )
    except IntegrityError:
        # Username (email) already taken in auth_user
        try:
            user = User.objects.get(username=email)
            user.set_password(password)
            user.save()
        except User.DoesNotExist:
            return {
                'success': False,
                'error': "Unable to create account. The email may already be in use. Please contact support.",
            }

    # ── Create Agent record ─────────────────────────────────────────
    try:
        # Map segments to the format used by the existing system
        user_types = []
        if 'health' in segments:
            user_types.append('health')
        if 'life' in segments:
            user_types.append('life')
        if 'motor' in segments:
            user_types.append('motor')
        if 'sme' in segments:
            user_types.append('sme')

        agent = Agent.objects.create(
            user=user,
            fullname=fullname,
            email=email,
            mobile=mobile,
            status='active',
            plan_type='free_trial',
            registration_step=3,  # Mark as fully registered
            user_types=user_types,
            experience_range=experience_range,
            agent_pincode=agent_pincode,
            registration_draft={
                'source': 'whatsapp_bot',
                'state': state,
                'segments': segments,
            },
        )

        # Try to set the state field if it exists on the profile
        # (the Agent model stores state in registration_draft)

        # Build login URL
        site_url = os.environ.get('WA_BOT_SITE_URL', os.environ.get('APP_URL', 'http://localhost:8000')).rstrip('/')
        login_url = f"{site_url}/agent-login/"

        logger.info(f"[WA-Bot] Created agent #{agent.id} for {email} via WhatsApp registration")

        return {
            'success': True,
            'agent': agent,
            'password': password,
            'login_url': login_url,
            'email': email,
        }

    except IntegrityError as e:
        logger.error(f"[WA-Bot] IntegrityError creating agent: {e}")
        # Clean up the user if agent creation failed
        try:
            user.delete()
        except Exception:
            pass
        return {
            'success': False,
            'error': "Unable to create your agent profile. The email or mobile may already be in use.",
        }
    except Exception as e:
        logger.error(f"[WA-Bot] Error creating agent: {e}")
        try:
            user.delete()
        except Exception:
            pass
        return {
            'success': False,
            'error': "An unexpected error occurred during registration. Please try again or contact support.",
        }
