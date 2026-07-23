"""
Google Business Profile (GBP) OAuth & API views.

Flow:
  1. /agent/gbp/auth/       — opens Google OAuth popup with business.manage scope
  2. /agent/gbp/callback/   — exchanges auth code, fetches GBP accounts/locations
  3. /agent/gbp/status/     — AJAX: returns current GBP link status for this agent
  4. /agent/gbp/save-url/   — AJAX POST: saves a manually-entered or auto-detected GBP URL

All views are completely isolated from the existing agent-login Google OAuth flow
(redirectToGoogle / handleGoogleCallback in auth.py).
"""

import json
import logging
import re
import urllib.parse
import datetime

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.agents.models import Agent, AgentProfile

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_agent_and_profile(request):
    """Return (agent, profile) for the currently logged-in user, or (None, None)."""
    user = request.user
    agent = Agent.objects.filter(user=user).first()
    if not agent:
        return None, None
    profile, _ = AgentProfile.objects.get_or_create(agent=agent)
    return agent, profile


def _refresh_gbp_token(profile):
    """
    Use the stored refresh_token to obtain a new access_token.
    Updates profile in-place (does NOT call profile.save() — caller must do that).
    Returns the new access_token string, or None on failure.
    """
    import requests as http_requests

    refresh_token = profile.gbp_refresh_token
    if not refresh_token:
        return None

    try:
        resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id":     getattr(settings, "GOOGLE_CLIENT_ID", ""),
                "client_secret": getattr(settings, "GOOGLE_CLIENT_SECRET", ""),
                "refresh_token": refresh_token,
                "grant_type":    "refresh_token",
            },
            timeout=10,
        )
        if not resp.ok:
            logger.warning("GBP token refresh failed: %s", resp.text[:200])
            return None
        data = resp.json()
        profile.gbp_access_token = data.get("access_token", "")
        expires_in = data.get("expires_in", 3600)
        profile.gbp_token_expires_at = (
            datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))
        )
        return profile.gbp_access_token
    except Exception as exc:
        logger.error("GBP token refresh error: %s", exc)
        return None


def _get_valid_access_token(profile):
    """
    Return a valid access token for the profile, refreshing if necessary.
    Returns None if no token is available.
    """
    now = datetime.datetime.utcnow()
    token_exp = profile.gbp_token_expires_at

    # Token exists and is still valid (with 5-min buffer)
    if profile.gbp_access_token and token_exp:
        if isinstance(token_exp, datetime.datetime):
            expires_naive = token_exp.replace(tzinfo=None) if token_exp.tzinfo else token_exp
        else:
            expires_naive = token_exp
        if expires_naive > now + datetime.timedelta(minutes=5):
            return profile.gbp_access_token

    # Try to refresh
    new_token = _refresh_gbp_token(profile)
    if new_token:
        profile.save(update_fields=["gbp_access_token", "gbp_token_expires_at"])
    return new_token


def _fetch_gbp_locations(access_token):
    """
    Use the GBP API to list all accounts and their locations for this token.
    Returns a list of dicts: [{name, title, maps_url}, ...] or [].
    """
    import requests as http_requests

    headers = {"Authorization": f"Bearer {access_token}"}
    locations = []

    try:
        # Step 1: list accounts
        accts_resp = http_requests.get(
            "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
            headers=headers,
            timeout=10,
        )
        if not accts_resp.ok:
            logger.warning("GBP accounts list failed: %s", accts_resp.text[:300])
            return locations

        accounts = accts_resp.json().get("accounts", [])

        for account in accounts:
            acct_name = account.get("name", "")
            if not acct_name:
                continue

            # Step 2: list locations for this account
            locs_resp = http_requests.get(
                f"https://mybusinessbusinessinformation.googleapis.com/v1/{acct_name}/locations",
                params={"readMask": "name,title,metadata"},
                headers=headers,
                timeout=10,
            )
            if not locs_resp.ok:
                logger.warning(
                    "GBP locations list failed for %s: %s",
                    acct_name,
                    locs_resp.text[:300],
                )
                continue

            for loc in locs_resp.json().get("locations", []):
                title   = loc.get("title", "")
                metadata = loc.get("metadata", {})
                maps_url  = metadata.get("mapsUrl") or metadata.get("newReviewUrl", "")
                place_id  = metadata.get("placeId", "")

                # Build a stable Maps URL using place ID when available
                if place_id:
                    maps_url = f"https://maps.google.com/?cid={place_id}"
                elif not maps_url:
                    maps_url = ""

                locations.append({"name": title, "maps_url": maps_url})

    except Exception as exc:
        logger.error("GBP fetch locations error: %s", exc)

    return locations


def _build_gbp_create_url(agent):
    """
    Build the URL to open on Google for creating a new Business Profile.
    Pre-fills as much as Google allows (which is limited to the base URL).
    Returns the URL string.
    """
    # Google's creation page doesn't accept pre-fill query params,
    # so we just return the base creation URL.
    return "https://business.google.com/create"


def _is_valid_gbp_url(url):
    """Return True if the URL looks like a legitimate Google Business / Maps URL."""
    if not url or not isinstance(url, str):
        return False
    patterns = [
        r"maps\.google\.",
        r"google\..+/maps",
        r"business\.google\.com",
        r"g\.page/",
        r"goo\.gl/maps",
        r"maps\.app\.goo\.gl",
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)


# ── Popup result HTML ─────────────────────────────────────────────────────────

def _popup_result_html(result_dict):
    """
    Return a self-closing HTML page that sends a postMessage to the opener window
    and then closes itself.
    """
    result_json = json.dumps(result_dict)
    html = f"""<!DOCTYPE html>
<html>
<head><title>Connecting to Google Business...</title></head>
<body style="font-family:sans-serif;text-align:center;padding:40px;">
<p>Authorization complete. This window will close automatically.</p>
<script>
(function() {{
    var result = {result_json};
    result.type = 'gbp_result';
    try {{
        if (window.opener) {{
            window.opener.postMessage(result, '*');
        }}
    }} catch(e) {{}}
    window.close();
}})();
</script>
</body>
</html>"""
    return html


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required(login_url='agents:agent_login')
def agent_gbp_auth(request):
    """
    Initiate Google OAuth popup for Google Business Profile (business.manage scope).
    This uses GBP_REDIRECT_URI (not GOOGLE_REDIRECT_URI) so it doesn't collide
    with the existing agent-login OAuth flow.
    """
    client_id    = getattr(settings, "GOOGLE_CLIENT_ID", "")
    redirect_uri = getattr(settings, "GBP_REDIRECT_URI", "")

    if not client_id or not redirect_uri:
        logger.error("GBP OAuth config missing: GOOGLE_CLIENT_ID or GBP_REDIRECT_URI not set.")
        return HttpResponse(
            "Google Business Profile OAuth configuration is missing. "
            "Please set GBP_REDIRECT_URI in your .env file.",
            status=500,
        )

    # Embed agent ID in state for the callback
    agent, _ = _get_agent_and_profile(request)
    agent_id  = agent.id if agent else ""

    params = {
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "response_type": "code",
        "scope":         "openid email profile https://www.googleapis.com/auth/business.manage",
        "state":         f"gbp_{agent_id}",
        "access_type":   "offline",
        "prompt":        "consent",   # force refresh_token even if previously authorized
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    from django.shortcuts import redirect as django_redirect
    return django_redirect(auth_url)


def agent_gbp_callback(request):
    """
    Handle the OAuth callback for Google Business Profile.
    - Exchanges auth code for access + refresh tokens
    - Lists GBP accounts/locations
    - Saves tokens + GBP URL to AgentProfile
    - Returns a self-closing popup HTML that posts result to opener
    """
    import requests as http_requests

    error = request.GET.get("error")
    if error:
        logger.warning("GBP OAuth error returned: %s", error)
        return HttpResponse(
            _popup_result_html({"status": "error", "message": error}),
            content_type="text/html",
        )

    code  = request.GET.get("code")
    state = request.GET.get("state", "")

    if not code:
        return HttpResponse(
            _popup_result_html({"status": "error", "message": "Authorization code missing."}),
            content_type="text/html",
        )

    # Extract agent_id from state (format: "gbp_<agent_id>")
    agent_id_str = state.replace("gbp_", "").strip()
    agent = None
    profile = None
    if agent_id_str.isdigit():
        agent = Agent.objects.filter(id=int(agent_id_str)).first()
        if agent:
            profile, _ = AgentProfile.objects.get_or_create(agent=agent)

    client_id     = getattr(settings, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    redirect_uri  = getattr(settings, "GBP_REDIRECT_URI", "")

    try:
        # ── Exchange code for tokens ──────────────────────────────────────────
        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     client_id,
                "client_secret": client_secret,
                "redirect_uri":  redirect_uri,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )
        if not token_resp.ok:
            logger.error("GBP token exchange failed: %s", token_resp.text[:300])
            return HttpResponse(
                _popup_result_html({"status": "error", "message": "Token exchange failed."}),
                content_type="text/html",
            )

        tokens        = token_resp.json()
        access_token  = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        expires_in    = tokens.get("expires_in", 3600)

        # ── Persist tokens in AgentProfile ───────────────────────────────────
        if profile and access_token:
            profile.gbp_access_token    = access_token
            if refresh_token:
                profile.gbp_refresh_token = refresh_token
            profile.gbp_token_expires_at = (
                datetime.datetime.utcnow()
                + datetime.timedelta(seconds=int(expires_in))
            )
            profile.save(update_fields=[
                "gbp_access_token",
                "gbp_refresh_token",
                "gbp_token_expires_at",
            ])

        # ── Fetch GBP locations ───────────────────────────────────────────────
        locations = _fetch_gbp_locations(access_token) if access_token else []

        if locations:
            # Use the first location's Maps URL
            first = locations[0]
            gbp_url      = first.get("maps_url", "")
            business_name = first.get("name", "")

            # Save URL to social_links
            if profile and gbp_url:
                social = dict(profile.social_links or {})
                social["google_business"] = gbp_url
                profile.social_links = social
                profile.save(update_fields=["social_links"])

            return HttpResponse(
                _popup_result_html({
                    "status":        "found",
                    "url":           gbp_url,
                    "business_name": business_name,
                }),
                content_type="text/html",
            )

        # ── No listing found — build create URL ──────────────────────────────
        create_url = _build_gbp_create_url(agent) if agent else "https://business.google.com/create"
        return HttpResponse(
            _popup_result_html({
                "status":     "not_found",
                "create_url": create_url,
            }),
            content_type="text/html",
        )

    except Exception as exc:
        logger.error("GBP callback error: %s", exc, exc_info=True)
        return HttpResponse(
            _popup_result_html({"status": "error", "message": "An unexpected error occurred."}),
            content_type="text/html",
        )


@login_required(login_url='agents:agent_login')
def agent_gbp_status(request):
    """
    AJAX GET: return current GBP link status for the logged-in agent.
    """
    agent, profile = _get_agent_and_profile(request)
    if not agent or not profile:
        return JsonResponse({"status": "error", "message": "Agent not found."}, status=404)

    social   = profile.social_links or {}
    gbp_url  = social.get("google_business", "")
    has_toks = bool(profile.gbp_refresh_token)

    if gbp_url:
        return JsonResponse({
            "status":     "found",
            "gbp_url":    gbp_url,
            "has_tokens": has_toks,
        })

    return JsonResponse({
        "status":      "not_found",
        "has_tokens":  has_toks,
        "create_url":  _build_gbp_create_url(agent),
    })


@login_required(login_url='agents:agent_login')
@require_POST
def agent_gbp_save_url(request):
    """
    AJAX POST: save a manually-entered or confirmed GBP URL to agent profile.
    Body JSON: {"gbp_url": "https://maps.google.com/..."}
    """
    agent, profile = _get_agent_and_profile(request)
    if not agent or not profile:
        return JsonResponse({"status": "error", "message": "Agent not found."}, status=404)

    try:
        body    = json.loads(request.body or "{}")
        gbp_url = (body.get("gbp_url") or "").strip()
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"status": "error", "message": "Invalid JSON body."}, status=400)

    if not gbp_url:
        return JsonResponse({"status": "error", "message": "No URL provided."}, status=400)

    if not _is_valid_gbp_url(gbp_url):
        return JsonResponse(
            {"status": "error", "message": "URL does not appear to be a Google Maps or Business URL."},
            status=400,
        )

    social = dict(profile.social_links or {})
    social["google_business"] = gbp_url
    profile.social_links = social
    profile.save(update_fields=["social_links"])

    return JsonResponse({"status": "success", "gbp_url": gbp_url})
