"""Optional website and social-link checks for the edit-profile form."""
import re
from urllib.parse import urlunparse, urlparse

GOOGLE_BUSINESS_HOSTS = ('google.com', 'google.co.in', 'goo.gl', 'g.page', 'g.co', 'google')
LINKEDIN_HOSTS = ('linkedin.com', 'lnkd.in')
INSTAGRAM_HOSTS = ('instagram.com',)
FACEBOOK_HOSTS = ('facebook.com', 'fb.com', 'fb.me')
YOUTUBE_HOSTS = ('youtube.com', 'youtu.be')

_HOST_RE = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})$'
)
_TAIL_RE = re.compile(
    r'^[A-Za-z0-9.-]+(?::\d{2,5})?(?:[/?#][A-Za-z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]*)?$'
)
_SCHEME_RE = re.compile(r'^https?://', re.IGNORECASE)
_PORT_RE = re.compile(r':\d{2,5}$')


def web_url_host(url):
    """Return the hostname when url is http(s), www., or a plain domain link."""
    raw = (url or '').strip()
    if not raw:
        return ''
    if len(raw) > 255 or re.search(r'[\s<>\\]', raw) or re.search(r'[\x00-\x1f]', raw):
        return None
    lower = raw.lower()
    if lower.startswith(('javascript:', 'data:', 'ftp:', 'file:', 'mailto:')):
        return None
    if _SCHEME_RE.match(raw):
        candidate = raw
    else:
        first = raw.split('/', 1)[0]
        if raw.startswith('//') or (':' in first and not _PORT_RE.search(first)):
            return None
        candidate = 'https://' + raw
    parsed = urlparse(candidate)
    if (parsed.scheme or '').lower() not in ('http', 'https'):
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or '').strip().lower().rstrip('.')
    if not host:
        return None
    try:
        host = host.encode('idna').decode('ascii')
    except UnicodeError:
        return None
    if not _HOST_RE.fullmatch(host):
        return None
    rest = candidate.split('://', 1)[1]
    if not _TAIL_RE.fullmatch(rest):
        return None
    return host


def optional_web_url_error(url, hosts, label):
    """Empty is allowed. A filled value must be a real link, and may be limited to hosts."""
    raw = (url or '').strip()
    if not raw:
        return ''
    host = web_url_host(raw)
    if not host:
        return f'Enter a valid {label} link, such as https://example.com or www.example.com.'
    if hosts and not any(host == allowed or host.endswith('.' + allowed) for allowed in hosts):
        example_host = hosts[0]
        return f'Enter a valid {label} link, such as https://www.{example_host}/ or www.{example_host}.'
    return ''


def normalize_web_url(url):
    """
    Return a trimmed http(s) URL without credentials, or '' when empty.
    Raises ValueError when the value is non-empty but not a valid web URL.
    """
    raw = (url or '').strip()
    if not raw:
        return ''
    if optional_web_url_error(raw, None, 'link'):
        raise ValueError('invalid url')
    candidate = raw if _SCHEME_RE.match(raw) else f'https://{raw}'
    parsed = urlparse(candidate)
    scheme = (parsed.scheme or 'https').lower()
    hostname = (parsed.hostname or '').strip().lower().rstrip('.')
    try:
        hostname = hostname.encode('idna').decode('ascii')
    except UnicodeError as exc:
        raise ValueError('invalid url') from exc
    port = parsed.port
    netloc = hostname
    if port is not None and not (
        (scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)
    ):
        netloc = f'{hostname}:{port}'
    normalized = urlunparse((
        scheme,
        netloc,
        parsed.path or '',
        parsed.params or '',
        parsed.query or '',
        parsed.fragment or '',
    ))
    if len(normalized) > 255:
        raise ValueError('invalid url')
    return normalized


def _coerce_url_field(raw, error_key, hosts, label, errors, target):
    """Validate one optional URL field and write the normalized value into target."""
    value = (raw or '').strip()
    err = optional_web_url_error(value, hosts, label)
    if err:
        errors[error_key] = [err if err.endswith('.') else f'{err}.']
        return
    try:
        target[error_key] = normalize_web_url(value) if value else ''
    except ValueError:
        errors[error_key] = [
            f'Enter a valid {label} link, such as https://example.com or www.example.com.',
        ]


def process_digital_presence_for_save(
    *,
    website='',
    google_business='',
    linkedin='',
    instagram='',
    facebook='',
    youtube='',
):
    """
    Validate edit-profile digital presence fields (Django form names).
    Returns (errors, normalized_values) where normalized_values uses storage keys.
    """
    errors = {}
    storage = {
        'website': '',
        'google_business': '',
        'linkedin': '',
        'instagram': '',
        'facebook': '',
        'youtube': '',
    }
    specs = (
        ('website', website, None, 'website', 'website'),
        ('google_business', google_business, GOOGLE_BUSINESS_HOSTS, 'Google Business', 'google_business'),
        ('linkedin_url', linkedin, LINKEDIN_HOSTS, 'LinkedIn', 'linkedin'),
        ('instagram_url', instagram, INSTAGRAM_HOSTS, 'Instagram', 'instagram'),
        ('facebook_url', facebook, FACEBOOK_HOSTS, 'Facebook', 'facebook'),
        ('youtube_url', youtube, YOUTUBE_HOSTS, 'YouTube', 'youtube'),
    )
    for error_key, raw, hosts, label, storage_key in specs:
        bucket = {}
        _coerce_url_field(raw, error_key, hosts, label, bucket, bucket)
        if error_key in bucket and isinstance(bucket[error_key], list):
            errors[error_key] = bucket[error_key]
        else:
            storage[storage_key] = bucket.get(error_key, '')
    return errors, storage


_SOCIAL_LINK_FIELD_SPECS = (
    ('google_business', GOOGLE_BUSINESS_HOSTS, 'Google Business'),
    ('linkedin_url', LINKEDIN_HOSTS, 'LinkedIn'),
    ('linkedin', LINKEDIN_HOSTS, 'LinkedIn'),
    ('instagram_url', INSTAGRAM_HOSTS, 'Instagram'),
    ('instagram', INSTAGRAM_HOSTS, 'Instagram'),
    ('facebook_url', FACEBOOK_HOSTS, 'Facebook'),
    ('facebook', FACEBOOK_HOSTS, 'Facebook'),
    ('youtube_url', YOUTUBE_HOSTS, 'YouTube'),
    ('youtube', YOUTUBE_HOSTS, 'YouTube'),
)


def normalize_social_links_dict(data):
    """Validate optional social URLs in an API/dict payload. Returns (errors, normalized_dict)."""
    if not data:
        return {}, {}
    errors = {}
    out = dict(data)
    for key, hosts, label in _SOCIAL_LINK_FIELD_SPECS:
        if key not in out:
            continue
        bucket = {}
        _coerce_url_field(out.get(key), key, hosts, label, bucket, bucket)
        if key in bucket and isinstance(bucket[key], list):
            errors[key] = bucket[key]
        else:
            out[key] = bucket.get(key, '')
    return errors, out


def apply_digital_presence_api(website, social_links):
    """
    Validate website + social payload (FastAPI / mobile).
    Returns (errors, website_norm, social_norm) — social_norm keeps the caller's keys.
    """
    social = dict(social_links or {})
    errors, storage = process_digital_presence_for_save(
        website=website,
        google_business=social.get('google_business', ''),
        linkedin=social.get('linkedin_url') or social.get('linkedin', ''),
        instagram=social.get('instagram_url') or social.get('instagram', ''),
        facebook=social.get('facebook_url') or social.get('facebook', ''),
        youtube=social.get('youtube_url') or social.get('youtube', ''),
    )
    if errors:
        return errors, None, None
    if 'google_business' in social:
        social['google_business'] = storage['google_business']
    if 'linkedin_url' in social:
        social['linkedin_url'] = storage['linkedin']
    if 'linkedin' in social:
        social['linkedin'] = storage['linkedin']
    if 'instagram_url' in social:
        social['instagram_url'] = storage['instagram']
    if 'instagram' in social:
        social['instagram'] = storage['instagram']
    if 'facebook_url' in social:
        social['facebook_url'] = storage['facebook']
    if 'facebook' in social:
        social['facebook'] = storage['facebook']
    if 'youtube_url' in social:
        social['youtube_url'] = storage['youtube']
    if 'youtube' in social:
        social['youtube'] = storage['youtube']
    return {}, storage['website'], social
