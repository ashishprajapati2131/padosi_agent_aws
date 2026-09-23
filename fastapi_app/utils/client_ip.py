"""Client IP resolution shared by the FastAPI middlewares and services.

Mirrors apps.admin_panel.middleware.client_ip_from_forwarded_for without
importing Django apps.
"""
import ipaddress

TRUSTED_PROXY_HOSTS = ("127.0.0.1", "::1", "testclient")


def client_ip_from_forwarded_for(x_forwarded_for: str) -> str:
    """Right-most public hop of an X-Forwarded-For chain from a trusted proxy.

    Proxies append the address they saw, so left-most entries are client
    supplied; taking entry [0] let anyone spoof their IP.
    """
    valid = []
    for hop in (x_forwarded_for or "").split(","):
        hop = hop.strip()
        if not hop:
            continue
        try:
            valid.append((hop, ipaddress.ip_address(hop)))
        except ValueError:
            continue
    for hop, addr in reversed(valid):
        if not (addr.is_private or addr.is_loopback or addr.is_link_local):
            return hop
    if valid:
        return valid[0][0]
    return "127.0.0.1"


def get_client_ip(request) -> str:
    """Trust X-Forwarded-For only when the direct peer is the local proxy."""
    client_host = request.client.host if getattr(request, "client", None) else "127.0.0.1"
    forwarded = request.headers.get("x-forwarded-for")
    if client_host in TRUSTED_PROXY_HOSTS and forwarded:
        return client_ip_from_forwarded_for(forwarded)
    return client_host
