"""
Cloudflare Cache Management Service for PadosiAgent Admin Panel.
Handles cache purging via Cloudflare v4 REST API and dashboard deep linking.
"""
import json
import logging
import urllib.request
import urllib.error
from django.conf import settings
from apps.home.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNT_ID = "64503f055289a96299db0c2bc0dc973c"
DEFAULT_DASHBOARD_PURGE_URL = (
    f"https://dash.cloudflare.com/{DEFAULT_ACCOUNT_ID}/padosiagent.com/caching/configuration"
)


def get_credentials():
    """
    Retrieves Cloudflare Zone ID and API Token from settings, environment, or SiteSetting.
    """
    zone_id = (
        getattr(settings, "CLOUDFLARE_ZONE_ID", "")
        or SiteSetting.get_value("cloudflare_zone_id", "")
        or ""
    ).strip()

    api_token = (
        getattr(settings, "CLOUDFLARE_API_TOKEN", "")
        or SiteSetting.get_value("cloudflare_api_token", "")
        or ""
    ).strip()

    return zone_id, api_token


def is_configured():
    """
    Returns True if both Zone ID and API Token are configured.
    """
    zone_id, api_token = get_credentials()
    return bool(zone_id and api_token)


def get_purge_url():
    """
    Returns the direct link to Cloudflare Dashboard Purge page.
    """
    return getattr(settings, "CLOUDFLARE_PURGE_URL", DEFAULT_DASHBOARD_PURGE_URL)


def purge_cache(urls=None):
    """
    Purges Cloudflare Edge Cache for padosiagent.com.
    If urls is None or empty, purges everything (purge_everything=True).
    If urls is provided, purges only specified URL list.

    Returns:
        (success: bool, message: str)
    """
    zone_id, api_token = get_credentials()

    if not zone_id or not api_token:
        return (
            False,
            "Cloudflare API credentials (Zone ID & API Token) are not configured. "
            "Please use the Cloudflare Dashboard link or add credentials in Settings."
        )

    endpoint = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"

    if urls:
        if isinstance(urls, str):
            urls = [urls]
        payload = {"files": list(urls)}
    else:
        payload = {"purge_everything": True}

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "User-Agent": "PadosiAgent-Admin/1.0",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data_bytes, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=12) as response:
            res_body = response.read().decode("utf-8")
            result = json.loads(res_body)

            if result.get("success"):
                logger.info("Cloudflare cache purged successfully for zone %s", zone_id)
                return True, "Cloudflare edge cache successfully purged across all global servers!"
            else:
                errors = result.get("errors", [])
                err_msg = ", ".join([e.get("message", str(e)) for e in errors]) or "Unknown API error"
                logger.error("Cloudflare purge API returned failure: %s", err_msg)
                return False, f"Cloudflare API error: {err_msg}"

    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            err_json = json.loads(err_body)
            errors = err_json.get("errors", [])
            err_msg = ", ".join([item.get("message", str(item)) for item in errors])
        except Exception:
            err_msg = str(e)
        logger.error("HTTPError calling Cloudflare purge API: %s", err_msg)
        return False, f"Cloudflare API HTTP error ({e.code}): {err_msg}"

    except urllib.error.URLError as e:
        logger.error("URLError calling Cloudflare purge API: %s", e.reason)
        return False, f"Network connection error to Cloudflare: {e.reason}"

    except Exception as e:
        logger.exception("Unexpected error purging Cloudflare cache")
        return False, f"Failed to purge Cloudflare cache: {e}"


def save_credentials(zone_id, api_token):
    """
    Saves Cloudflare credentials into SiteSetting.
    """
    SiteSetting.set_value("cloudflare_zone_id", zone_id.strip(), group="security")
    SiteSetting.set_value("cloudflare_api_token", api_token.strip(), group="security")
    return True

