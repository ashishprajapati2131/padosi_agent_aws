"""
On/off switches for the WhatsApp bot's conversation flows, flipped from Admin → WhatsApp & OpenWA Hub.

A switch only decides whether a NEW conversation may start that flow. Someone already in the
middle of it (e.g. waiting on a payment link) can still finish.
"""

REGISTRATION = "wa_flow_registration_enabled"
LIAFI = "liafi_enabled"
LIAFI_EVENT_MODE = "liafi_event_mode"

FLOWS = [
    {
        "key": REGISTRATION,
        "label": "Agent registration",
        "help": "hi / register → 7-step signup and plan payment",
        "default": True,
    },
    {
        "key": LIAFI,
        "label": "LIAFI event flow",
        "help": "Agents send LIAFI to register for the LIAFI General Council Meeting",
        "default": True,
    },
    {
        "key": LIAFI_EVENT_MODE,
        "label": "LIAFI event mode",
        "help": "Every new chat (hi, hello…) starts the LIAFI flow. Needs the LIAFI flow ON.",
        "default": False,
    },
]
_DEFAULTS = {f["key"]: f["default"] for f in FLOWS}


def is_on(key):
    from apps.home.models.site_setting import SiteSetting

    value = SiteSetting.get_value(key, _DEFAULTS[key])
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def all_switches():
    return [{**f, "enabled": is_on(f["key"])} for f in FLOWS]


def set_switch(key, enabled):
    """Returns False for an unknown key.

    Event mode only works with the LIAFI flow on, so the two are kept consistent: event mode ON
    turns the LIAFI flow on, LIAFI flow OFF turns event mode off.
    """
    if key not in _DEFAULTS:
        return False
    from apps.home.models.site_setting import SiteSetting

    enabled = bool(enabled)
    SiteSetting.set_value(key, enabled, group="whatsapp")
    if key == LIAFI_EVENT_MODE and enabled:
        SiteSetting.set_value(LIAFI, True, group="whatsapp")
    if key == LIAFI and not enabled:
        SiteSetting.set_value(LIAFI_EVENT_MODE, False, group="whatsapp")
    return True
