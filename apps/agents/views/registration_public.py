"""Passwordless public signups (quick client register, Facebook ad signup) and their portal-account guards."""

import json
import re
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from apps.agents.models import Agent

from .registration_common import logger


def _email_belongs_to_portal_account(email):
    """True when an email is (or will be) a non-client portal identity.

    resolve_agent_for_user() links an agent to ANY auth_user with the same
    email, so a passwordless client account must never be created or signed in
    for an agent / insurance / distributor / staff email.
    """
    from django.contrib.auth.models import User
    from apps.agents.models import Agent

    if not email:
        return False
    if Agent.objects.filter(email__iexact=email).exists():
        return True
    return any(_is_portal_user(u) for u in User.objects.filter(email__iexact=email))


def _is_portal_user(user):
    """Staff, agent, insurance or distributor users — never passwordless-login targets."""
    from apps.agents.models import Agent

    if not user:
        return False
    if user.is_staff or user.is_superuser:
        return True
    if Agent.objects.filter(user=user).exists():
        return True
    if user.email and Agent.objects.filter(email__iexact=user.email).exists():
        return True
    if hasattr(user, "insurance_profile"):
        return True
    if (
        getattr(user, "role", None) == "distributor"
        or user.groups.filter(name="distributor").exists()
    ):
        return True
    return False


def _safe_local_redirect(request, url, default="/find-agents/"):
    from django.utils.http import url_has_allowed_host_and_scheme

    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    return default


@require_POST
@csrf_protect
def client_quick_register(request):
    """
    Client quick registration view. Replicates Laravel's ClientRegistrationController.quickRegister().
    Validates input, logins existing client, or creates a new client and user account.

    Sign-in here is passwordless, so it is only ever done for plain client
    accounts. Agent / insurance / distributor / staff accounts get the guest
    lead session only — never a login (this was an account takeover).
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = request.POST

    fullname = (data.get("fullname") or "").strip()
    email = (data.get("email") or "").strip().lower()
    mobile = (data.get("mobile") or "").strip()
    pincode = (data.get("pincode") or "").strip() or None

    # Validation
    errors = {}
    if not fullname:
        errors["fullname"] = ["Full name is required."]
    elif len(fullname) < 2 or len(fullname) > 100:
        errors["fullname"] = ["Name must be between 2 and 100 characters."]
    elif not re.match(r"^[\w\s.\-\']+$", fullname):
        errors["fullname"] = [
            "Name may only contain letters, spaces, dots, hyphens or apostrophes."
        ]

    if not email:
        errors["email"] = ["Email is required."]
    elif "@" not in email:
        errors["email"] = ["Please enter a valid email address."]

    if not mobile:
        errors["mobile"] = ["Mobile number is required."]
    elif len(mobile) != 10 or not mobile.isdigit():
        errors["mobile"] = ["Mobile number must be exactly 10 digits."]
    elif not re.match(r"^[6-9][0-9]{9}$", mobile):
        errors["mobile"] = [
            "Please enter a valid Indian mobile number (starts with 6-9)."
        ]

    if pincode and (len(pincode) != 6 or not pincode.isdigit()):
        errors["pincode"] = ["Pincode must be exactly 6 digits."]

    if errors:
        return JsonResponse(
            {
                "success": False,
                "message": "Please fix the validation errors below.",
                "errors": errors,
            },
            status=422,
        )

    from django.contrib.auth.models import User
    from apps.agents.models import Client, Agent
    from apps.agents.services.account_auth import DJANGO_AUTH_BACKEND

    existing_user = User.objects.filter(email=email).first()
    if not existing_user and mobile:
        existing_client = (
            Client.objects.filter(mobile=mobile).select_related("user").first()
        )
        if existing_client and existing_client.user:
            existing_user = existing_client.user
        else:
            existing_agent = (
                Agent.objects.filter(mobile=mobile).select_related("user").first()
            )
            if existing_agent and existing_agent.user:
                existing_user = existing_agent.user

    # A logged-in agent (or distributor) must not be converted into a client or
    # have their portal session hijacked when they use the client quick-register.
    current_is_logged_in_agent = (
        request.user.is_authenticated
        and Agent.objects.filter(user=request.user).exists()
    )

    redirect_to = _safe_local_redirect(request, data.get("redirect_url"))

    if existing_user and _is_portal_user(existing_user):
        # Privileged identity: keep the lead-capture session data the visitor
        # typed, but never mutate or sign in the portal account.
        request.session["quick_lead_user"] = {
            "fullname": fullname,
            "email": email,
            "mobile": mobile,
            "pincode": pincode,
        }
        request.session.modified = True
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "message": "Welcome back! Redirecting...",
                "redirect": redirect_to,
            }
        )

    if existing_user:
        # Plain client account: portal accounts are already handled by _is_portal_user above.
        is_client = Client.objects.filter(user=existing_user).exists()
        if not is_client:
            Client.objects.create(user=existing_user, mobile=mobile, pincode=pincode)
        elif mobile:
            Client.objects.filter(user=existing_user, mobile__isnull=True).update(
                mobile=mobile
            )

        request.session["quick_lead_user"] = {
            "fullname": fullname
            or getattr(existing_user, "fullname", "")
            or existing_user.get_full_name()
            or existing_user.username,
            "email": existing_user.email or email,
            "mobile": mobile,
            "pincode": pincode,
        }
        # Typing an email/mobile proves nothing, so an existing account is never
        # signed in here (account takeover); the lead session is enough to contact agents.
        request.session.modified = True

        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "message": "Welcome back! Redirecting...",
                "redirect": redirect_to,
            }
        )

    if _email_belongs_to_portal_account(email):
        # e.g. an agent that has no auth_user yet: creating one with this email
        # would let the visitor inherit that agent on next request.
        request.session["quick_lead_user"] = {
            "fullname": fullname,
            "email": email,
            "mobile": mobile,
            "pincode": pincode,
        }
        request.session.modified = True
        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "message": "Welcome back! Redirecting...",
                "redirect": redirect_to,
            }
        )

    # Create new client account
    from django.db import transaction

    try:
        with transaction.atomic():
            # Create standard User
            username = email.split("@")[0]
            counter = 1
            base_username = username
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            # No password: client sign-in is passwordless, and password=email
            # was guessable by anyone who knew the address.
            user = User.objects.create_user(
                username=username,
                email=email,
                password=None,
                first_name=fullname.split(" ")[0],
                last_name=" ".join(fullname.split(" ")[1:]),
            )

            # Create Client record
            Client.objects.create(user=user, mobile=mobile, pincode=pincode)

        # Log user in
        from django.contrib.auth import login
        from apps.distributors.views.dashboard import is_distributor

        if (
            not (request.user.is_authenticated and is_distributor(request.user))
            and not current_is_logged_in_agent
        ):
            login(request, user, backend=DJANGO_AUTH_BACKEND)

        request.session["quick_lead_user"] = {
            "fullname": fullname,
            "email": email,
            "mobile": mobile,
            "pincode": pincode,
        }
        request.session.modified = True

        return JsonResponse(
            {
                "success": True,
                "status": "success",
                "message": "Registration successful! Redirecting...",
                "redirect": redirect_to,
            }
        )

    except Exception as e:
        logger.error(f"Client quick registration failed: {e}")
        return JsonResponse(
            {
                "success": False,
                "status": "error",
                "message": "Unable to complete registration right now. Please try again.",
            },
            status=500,
        )


def fb_ad_signup(request):
    """
    Dedicated landing page and signup flow for Facebook Ads.
    Mirrors client_quick_register but fixes the password=email security issue,
    adds a transaction guard for concurrent email signups, and blocks agent accounts.
    """
    if request.method == "GET":
        return render(request, "public/fb_ad_signup.html")

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = request.POST

    fullname = (data.get("fullname") or "").strip()
    email = (data.get("email") or "").strip().lower()
    mobile = (data.get("mobile") or "").strip()
    pincode = (data.get("pincode") or "").strip()

    # --- Validation ---
    errors = {}
    if not fullname:
        errors["fullname"] = ["Full name is required."]
    elif len(fullname) < 2 or len(fullname) > 100:
        errors["fullname"] = ["Name must be between 2 and 100 characters."]
    elif not re.match(r"^[\w\s.\-\']+$", fullname):
        errors["fullname"] = [
            "Name may only contain letters, spaces, dots, hyphens or apostrophes."
        ]

    if not email:
        errors["email"] = ["Email is required."]
    elif "@" not in email:
        errors["email"] = ["Please enter a valid email address."]

    if not mobile:
        errors["mobile"] = ["Mobile number is required."]
    elif len(mobile) != 10 or not mobile.isdigit():
        errors["mobile"] = ["Mobile number must be exactly 10 digits."]
    elif not re.match(r"^[6-9][0-9]{9}$", mobile):
        errors["mobile"] = ["Please enter a valid Indian mobile number."]

    if not pincode:
        errors["pincode"] = ["Pincode is required."]
    elif len(pincode) != 6 or not pincode.isdigit():
        errors["pincode"] = ["Pincode must be exactly 6 digits."]

    if errors:
        return JsonResponse(
            {
                "success": False,
                "message": "Please fix the validation errors below.",
                "errors": errors,
            },
            status=422,
        )

    from django.contrib.auth.models import User
    from apps.agents.models import Client
    from django.contrib.auth import login
    from django.db import transaction

    try:
        with transaction.atomic():
            # Guard against duplicates via select_for_update if existing, else create carefully
            existing_user = User.objects.select_for_update().filter(email=email).first()

            # Security Check: this passwordless consumer flow must never sign in
            # (or create a look-alike of) an agent/insurance/distributor/staff
            # account — only plain client accounts.
            if _is_portal_user(existing_user) or (
                not existing_user and _email_belongs_to_portal_account(email)
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "status": "error",
                        "message": "This email is already registered with another PadosiAgent portal — please use that login page.",
                    },
                    status=403,
                )

            if existing_user:
                is_client = Client.objects.filter(user=existing_user).exists()
                if not is_client:
                    Client.objects.create(
                        user=existing_user, mobile=mobile, pincode=pincode
                    )
                user_to_login = existing_user
                created_now = False
                message = "Welcome back! Redirecting..."
            else:
                username = email.split("@")[0]
                counter = 1
                base_username = username
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}{counter}"
                    counter += 1

                user_to_login = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=fullname.split(" ")[0],
                    last_name=" ".join(fullname.split(" ")[1:]),
                )

                # MODIFICATION 1: Avoid setting password to email for security
                user_to_login.set_unusable_password()
                user_to_login.save()

                Client.objects.create(
                    user=user_to_login, mobile=mobile, pincode=pincode
                )
                created_now = True
                message = "Registration successful! Redirecting..."

    except Exception as e:
        logger.error(f"FB Ad quick registration failed: {e}")
        return JsonResponse(
            {
                "success": False,
                "status": "error",
                "message": "Unable to complete registration right now. Please try again.",
            },
            status=500,
        )

    # Set session for agent_capture_lead compatibility
    request.session["quick_lead_user"] = {
        "fullname": fullname,
        "email": email,
        "mobile": mobile,
        "pincode": pincode,
    }

    # Typing an email proves nothing, so an existing account is never signed
    # in here; the lead details above are enough to contact agents.
    if created_now:
        login(request, user_to_login)

    return JsonResponse(
        {
            "success": True,
            "status": "success",
            "message": message,
            "redirect": f"/find-agents/?pincode={pincode}",
        }
    )
