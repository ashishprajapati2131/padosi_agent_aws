"""Generate WhatsApp / Open Graph share cards that match the public agent card."""
import io
import math
import os
import re

from PIL import Image, ImageDraw, ImageFont
from django.conf import settings

from apps.agents.models import AgentProfile, AgentPerformanceStat

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE = Image.LANCZOS

TAG_COLORS = {
    'health': ((255, 241, 242), (190, 18, 60), (254, 205, 211)),
    'life': ((245, 243, 255), (124, 58, 237), (221, 214, 254)),
    'motor': ((239, 246, 255), (29, 78, 216), (191, 219, 254)),
    'sme': ((255, 251, 235), (180, 83, 9), (253, 230, 138)),
}
TAG_DEFAULT = ((243, 244, 246), (55, 65, 81), (229, 231, 235))

SEGMENT_DISPLAY_MAP = {
    'health': 'Health',
    'motor': 'Motor',
    'life': 'Life',
    'sme': 'SME Insurance',
    'travel': 'Travel',
    'marine': 'Marine',
    'fire': 'Fire Insurance',
    'general': 'General Insurance',
    'commercial': 'Commercial',
}

PILL_COLORS = {
    'health': ((255, 241, 242), (253, 164, 175), (225, 29, 72)),
    'life': ((245, 243, 255), (196, 181, 253), (124, 58, 237)),
    'motor': ((239, 246, 255), (147, 197, 253), (37, 99, 235)),
    'sme': ((255, 251, 235), (252, 211, 77), (217, 119, 6)),
}


def _agent_segment_pills(agent):
    """Return [{name, class}, ...] from the agent's real segments. Empty if none."""
    import re
    raw_tags = []
    ordered = getattr(agent, 'ordered_insurance_segments', None)
    if ordered is not None and not hasattr(ordered, '_mock_return_value'):
        try:
            raw_tags = list(ordered or [])
        except Exception:
            raw_tags = []
    if not raw_tags and hasattr(agent, 'insuranceSegments') and not hasattr(agent.insuranceSegments, '_mock_return_value'):
        try:
            raw_tags = [
                getattr(s, 'segment_type', None) or getattr(s, 'segment_name', str(s))
                for s in agent.insuranceSegments.all()
            ]
        except Exception:
            raw_tags = []

    cleaned_segments = []
    seen_classes = set()
    for t in raw_tags:
        clean_key = re.sub(r'[{}\s%|"\']', '', str(t)).lower()
        if 'ifseg' in clean_key or 'endif' in clean_key:
            continue
        matched_cls = 'default'
        display_name = None
        for known in ['health', 'motor', 'life', 'sme', 'travel', 'marine', 'fire', 'general', 'commercial']:
            if known in clean_key:
                matched_cls = known
                display_name = SEGMENT_DISPLAY_MAP[known]
                break
        if not display_name:
            cleaned_word = re.sub(r'[^a-zA-Z0-9 ]', '', str(t)).strip()
            if cleaned_word and not cleaned_word.startswith('seg'):
                display_name = cleaned_word.title()
                matched_cls = 'default'
        if display_name and matched_cls not in seen_classes:
            seen_classes.add(matched_cls)
            cleaned_segments.append({'name': display_name, 'class': matched_cls})
    return cleaned_segments


import base64
import logging
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

def _safe_str(val, default=""):
    """Safely extract string, ignoring unassigned MagicMock attributes in tests."""
    if val is None or hasattr(val, '_mock_return_value'):
        return default
    try:
        s = str(val).strip()
        return s if s else default
    except Exception:
        return default

def _share_card_place(agent, profile=None):
    """City shown on the share card. Never invents Ahmedabad."""
    city = ''
    if not hasattr(agent, '_mock_return_value'):
        try:
            from apps.agents.services.agent_city import resolve_agent_city
            city = resolve_agent_city(agent)
        except Exception:
            city = ''
    if not city:
        city = _safe_str(getattr(profile, 'display_city', None)) or _safe_str(getattr(profile, 'city', None))
    city = city.split('+')[0].strip()
    if not city:
        return ''  # no city saved: the card shows no location rather than a made-up one
    if 'india' in city.lower():
        return city
    return f'{city}, India'


def _safe_num(val, default=0):
    """Safely extract float/int, ignoring unassigned MagicMock attributes in tests."""
    if val is None or hasattr(val, '_mock_return_value'):
        return default
    try:
        return float(val)
    except Exception:
        return default


def _share_experience_years(agent, profile):
    """Years printed on the WhatsApp card.

    Same source as the public profile: the number the agent saved
    (experience_range). Profile.experience_years is used only when that
    field is empty.
    """
    range_raw = _safe_str(getattr(agent, 'experience_range', None))
    if range_raw:
        match = re.search(r'(\d+)', range_raw)
        if match:
            parsed = int(match.group(1))
            if parsed > 0:
                return parsed
    if profile is not None:
        profile_years = int(_safe_num(getattr(profile, 'experience_years', None), 0))
        if profile_years > 0:
            return profile_years
    return 0


def _shown(profile, flag):
    """Agent's own show_* privacy toggle (missing profile or field = shown)."""
    val = getattr(profile, flag, True) if profile is not None else True
    return val is not False and not hasattr(val, '_mock_return_value')


def _load_card_sources(agent, profile=None, perf=None):
    if profile is None:
        try:
            profile = AgentProfile.objects.filter(agent=agent).first()
        except Exception:
            profile = getattr(agent, 'profile', None)
    if perf is None:
        try:
            perf = AgentPerformanceStat.objects.filter(agent=agent).first()
        except Exception:
            perf = None
    return profile, perf


def _card_data(agent, profile=None, perf=None):
    """
    Everything the share card shows, taken only from what the agent saved.
    Anything blank, zero or hidden by the agent's show_* toggles is left out (never a placeholder).
    """
    from apps.agents.models import format_indian_number

    profile, perf = _load_card_sources(agent, profile, perf)
    name = (_safe_str(getattr(profile, 'display_name', None)) or _safe_str(getattr(agent, 'fullname', None))
            or _safe_str(getattr(agent, 'full_name', None)) or 'Insurance Advisor')
    agency = _safe_str(getattr(profile, 'agency_name', None)) or _safe_str(getattr(agent, 'agency_name', None))

    review_count = 0
    rating = 0.0
    if _shown(profile, 'show_ratings'):
        review_count = int(_safe_num(getattr(agent, 'review_count', None), 0))
        rating = round(_safe_num(getattr(agent, 'average_rating', None), 0.0), 1) if review_count else 0.0

    stats = []
    exp_val = _share_experience_years(agent, profile)
    if exp_val and _shown(profile, 'show_experience'):
        stats.append((f'{exp_val}+', 'YEARS EXP', False))
    clients_raw = _safe_str(getattr(agent, 'client_base', None))
    if clients_raw and _shown(profile, 'show_client_base'):
        digits = re.sub(r'[^\d.]', '', clients_raw)
        if digits and _safe_num(digits) > 0:
            clients = format_indian_number(digits) if digits == clients_raw.strip() else clients_raw
            stats.append((clients if '+' in clients else f'{clients}+', 'CLIENTS', False))
    if perf is not None and _shown(profile, 'show_claims_stats'):
        claims = int(_safe_num(getattr(perf, 'claims_processed', None), 0))
        if claims > 0:
            stats.append((f'{format_indian_number(claims)}+', 'CLAIMS', False))
        amount = _safe_num(getattr(perf, 'claims_amount', None), 0)
        if amount > 0:
            stats.append((f"₹{format_indian_number(amount).replace(' ', '')}+", 'SETTLED', True))

    return {
        'name': name,
        'initial': name[0].upper(),
        'subtitle': f'Insurance & Financial Advisor · {agency}' if agency and agency.lower() != name.lower()
                    else 'Insurance & Financial Advisor',
        'location': _share_card_place(agent, profile),
        'show_licensed': bool(profile is not None and (_safe_str(getattr(profile, 'license_number', None))
                                                       or _safe_str(getattr(profile, 'arn_number', None)))),
        'show_trusted': bool(_safe_num(getattr(agent, 'is_trusted', False), 0)),
        'show_verified': bool(_safe_num(getattr(agent, 'is_verified_agent', False), 0)),
        'rating': rating,
        'review_count': review_count,
        'stats': stats,
        'segments': _agent_segment_pills(agent),
        # Identifies the photo so a new upload changes the image version.
        'photo_ref': (_safe_str(getattr(profile, 'profile_photo_url', None)) + '|'
                      + _safe_str(getattr(profile, 'profile_photo_path', None))),
    }


def card_version(agent):
    """Short hash of what the card shows; part of the og:image URL so WhatsApp refetches after a change."""
    import hashlib
    import json
    try:
        data = _card_data(agent)
    except Exception:
        return ''
    return hashlib.sha1(json.dumps(data, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:10]

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except (ImportError, Exception):
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False

from contextlib import contextmanager


@contextmanager
def _single_browser_slot():
    """Yield True if this process may launch Chromium now.

    This URL is public and crawled by link-preview bots. Each Chromium costs
    ~150-300 MB and many processes/threads. Several at once exceed the
    hosting account's memory/process limits, so only one may run
    server-wide. A concurrent render uses the Pillow card instead.
    """
    try:
        import fcntl
    except ImportError:  # Windows dev machines
        yield True
        return
    got = False
    lock_dir = os.path.join(settings.BASE_DIR, 'tmp')
    os.makedirs(lock_dir, exist_ok=True)
    with open(os.path.join(lock_dir, 'og_chromium.lock'), 'w') as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except OSError:
            got = False
        try:
            yield got
        finally:
            if got:
                fcntl.flock(fh, fcntl.LOCK_UN)

def render_agent_og_jpeg(agent):
    """Return JPEG bytes for a 1200x630 agent digital visiting card OG image using Playwright or Pillow."""
    # Social crawlers need a fast, reliable JPEG — Playwright/Chromium is often unavailable on shared hosting.
    if not getattr(settings, 'DEBUG', False):
        return _render_agent_og_jpeg_pillow(agent)

    profile, perf = _load_card_sources(agent)
    card = _card_data(agent, profile, perf)

    # Image processing
    photo_base64 = ""
    photo = _load_photo(agent, profile)
    if photo:
        if photo.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', photo.size, (255, 255, 255))
            if photo.mode == 'P':
                photo = photo.convert('RGBA')
            if photo.mode in ('RGBA', 'LA'):
                bg.paste(photo, mask=photo.split()[-1])
            else:
                bg.paste(photo)
            photo = bg
        elif photo.mode != 'RGB':
            photo = photo.convert('RGB')
        # Crisp sizing for 320x550 column
        photo.thumbnail((600, 800))
        buf = io.BytesIO()
        photo.save(buf, format='JPEG', quality=90)
        photo_base64 = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')

    logo_base64 = ""
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo.png')
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            logo_base64 = "data:image/png;base64," + base64.b64encode(f.read()).decode('utf-8')

    # Inject exact frontend CSS for 100% pixel-perfect match
    css_path = os.path.join(settings.BASE_DIR, 'static', 'css', 'agent-card-shared.css')
    inline_css = ""
    if os.path.exists(css_path):
        with open(css_path, 'r', encoding='utf-8') as f:
            inline_css = f.read()

    context = {
        'inline_css': inline_css,
        'photo_base64': photo_base64,
        'logo_base64': logo_base64,
        'agent_initial': card['initial'],
        'rating_int': max(1, min(5, int(round(card['rating'])))) if card['review_count'] else 0,
        **card,
    }

    if PLAYWRIGHT_AVAILABLE and sync_playwright is not None:
        with _single_browser_slot() as may_launch:
            if not may_launch:
                logger.info("OG render for agent %s: Chromium busy, using Pillow card", getattr(agent, 'id', None))
            else:
                try:
                    import sys, asyncio
                    if sys.platform == 'win32':
                        try:
                            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                        except Exception:
                            pass
                    html = render_to_string('agents/og_image.html', context)
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page(viewport={"width": 1200, "height": 630})
                        page.set_content(html)
                        try:
                            page.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass
                        jpeg_bytes = page.screenshot(type="jpeg", quality=95)
                        browser.close()
                    return jpeg_bytes
                except Exception as e:
                    logger.warning(f"Playwright OG rendering failed, falling back to Pillow: {e}")

    # Memory-safe, high-speed Pillow fallback
    return _render_agent_og_jpeg_pillow(agent, profile=profile, perf=perf)


def _render_agent_og_jpeg_pillow(agent, profile=None, perf=None):
    """Fast, lightweight in-memory Pillow 1200x630 OG digital visiting card (used in production)."""
    profile, perf = _load_card_sources(agent, profile, perf)
    card = _card_data(agent, profile, perf)

    # Full-bleed card: fills the whole 1200x630 frame so WhatsApp's preview shows it as large as possible.
    W, H = 1200, 630
    canvas = Image.new('RGB', (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    fonts = _load_fonts()

    # Left column: photo or initial avatar, full height
    photo_w = 380
    photo = _load_photo(agent, profile)
    if photo:
        if photo.mode in ('RGBA', 'LA', 'P'):
            bg = Image.new('RGB', photo.size, (255, 255, 255))
            if photo.mode == 'P':
                photo = photo.convert('RGBA')
            if photo.mode in ('RGBA', 'LA'):
                bg.paste(photo, mask=photo.split()[-1])
            else:
                bg.paste(photo)
            photo = bg
        elif photo.mode != 'RGB':
            photo = photo.convert('RGB')
        canvas.paste(_cover_crop(photo, photo_w, H), (0, 0))
    else:
        draw.rectangle([(0, 0), (photo_w, H)], fill=(30, 58, 138))
        initial = card['initial']
        iw, ih = _text_size(draw, initial, fonts['initial'])
        draw.text(((photo_w - iw) // 2, (H - ih) // 2 - 12), initial, font=fonts['initial'], fill=(255, 255, 255))

    # Right column
    rx = photo_w + 44
    right = W - 44
    col_w = right - rx

    # Badges the agent has earned, then the name sized to the space left
    badges = []
    if card['show_licensed']:
        badges.append(("Licensed", (238, 242, 255), (199, 210, 254), (67, 56, 202)))
    if card['show_trusted']:
        badges.append(("Trusted", (236, 253, 245), (167, 243, 208), (5, 150, 105)))
    badge_ws = [_text_size(draw, b[0], fonts['badge'])[0] + 28 for b in badges]
    badges_w = sum(badge_ws) + 12 * len(badges) + (16 if badges else 0)
    name_font = _shrink_font(draw, card['name'], fonts['name'], col_w - badges_w, 34)
    name = _fit_text(draw, card['name'], name_font, col_w - badges_w)
    draw.text((rx, 44 + (getattr(fonts['name'], 'size', 0) - getattr(name_font, 'size', 0)) // 2), name, font=name_font, fill=(15, 23, 42))
    nw, _ = _text_size(draw, name, name_font)
    bx, by = rx + nw + 16, 58
    for (label, fill, outline, color), bw in zip(badges, badge_ws):
        _rounded_rect(draw, [(bx, by), (bx + bw, by + 32)], radius=16, fill=fill, outline=outline, width=1)
        draw.text((bx + 14, by + 6), label, font=fonts['badge'], fill=color)
        bx += bw + 12

    draw.text((rx, 112), _fit_text(draw, card['subtitle'], fonts['sub'], col_w), font=fonts['sub'], fill=(100, 116, 139))

    # Rating (only with real approved reviews) and location (only if saved)
    meta_y = 164
    mx = rx
    if card['review_count']:
        _draw_star(draw, mx + 10, meta_y + 13, 10, fill=(245, 158, 11))
        score = f"{card['rating']:.1f}"
        draw.text((mx + 26, meta_y), score, font=fonts['meta_bold'], fill=(15, 23, 42))
        sw, _ = _text_size(draw, score, fonts['meta_bold'])
        count = f"({card['review_count']} review{'s' if card['review_count'] != 1 else ''})"
        draw.text((mx + 34 + sw, meta_y), count, font=fonts['meta'], fill=(100, 116, 139))
        cw, _ = _text_size(draw, count, fonts['meta'])
        mx += 34 + sw + cw + 32
    if card['location']:
        _draw_pin(draw, mx + 7, meta_y + 13, fill=(100, 116, 139))
        loc = _fit_text(draw, card['location'], fonts['meta'], right - (mx + 24))
        draw.text((mx + 24, meta_y), loc, font=fonts['meta'], fill=(100, 116, 139))
    has_meta = bool(card['review_count'] or card['location'])

    # Stat boxes: only the numbers the agent filled in, sharing the row width
    stat_y = 222 if has_meta else 170
    box_h, gap = 112, 16
    stats = card['stats']
    box_w = min((col_w - gap * (len(stats) - 1)) // len(stats), 260) if stats else 0
    for i, (val, lbl, is_green) in enumerate(stats):
        bx0 = rx + i * (box_w + gap)
        bg_fill = (240, 253, 244) if is_green else (248, 250, 252)
        border_col = (187, 247, 208) if is_green else (226, 232, 240)
        num_col = (21, 128, 61) if is_green else (15, 23, 42)
        lbl_col = (22, 101, 52) if is_green else (71, 85, 105)
        _rounded_rect(draw, [(bx0, stat_y), (bx0 + box_w, stat_y + box_h)], radius=16, fill=bg_fill, outline=border_col, width=2)
        # Numbers are never cut: the font shrinks to fit the box instead.
        num_font = _shrink_font(draw, val, fonts['stat_num'], box_w - 16, 18)
        vw, vh = _text_size(draw, val, num_font)
        draw.text((bx0 + (box_w - vw) // 2, stat_y + 14 + (getattr(fonts['stat_num'], 'size', 0) - getattr(num_font, 'size', 0)) // 2), val,
                  font=num_font, fill=num_col)
        lw, _ = _text_size(draw, lbl, fonts['stat_lbl'])
        draw.text((bx0 + (box_w - lw) // 2, stat_y + 70), lbl, font=fonts['stat_lbl'], fill=lbl_col)

    # Segment pills from the agent's real Health / Life / Motor / SME list (never past the column)
    pill_y = stat_y + box_h + 30 if stats else stat_y
    px = rx
    for item in card['segments'][:4]:
        p_bg, p_border, p_text = PILL_COLORS.get(item.get('class'), ((241, 245, 249), (203, 213, 225), (51, 65, 85)))
        pw, _ = _text_size(draw, item['name'], fonts['pill'])
        full_pw = pw + 36
        if px + full_pw > right:
            break
        _rounded_rect(draw, [(px, pill_y), (px + full_pw, pill_y + 44)], radius=22, fill=p_bg, outline=p_border, width=1)
        draw.text((px + 18, pill_y + 10), item['name'], font=fonts['pill'], fill=p_text)
        px += full_pw + 14

    # Footer strip pinned to the bottom
    draw.line([(rx, 540), (right, 540)], fill=(226, 232, 240), width=2)
    draw.text((rx, 562), "Direct WhatsApp & Calls · Zero middlemen", font=fonts['footer'], fill=(51, 65, 85))
    if card['show_verified']:
        label = "PadosiAgent Verified"
        lw, _ = _text_size(draw, label, fonts['footer_bold'])
        draw.text((right - lw, 561), label, font=fonts['footer_bold'], fill=(30, 58, 138))

    buf = io.BytesIO()
    canvas.save(buf, format='JPEG', quality=95)
    return buf.getvalue()


def _load_fonts():
    bold_paths = [
        r'C:\Windows\Fonts\segoeuib.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'arialbd.ttf'),
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans-Bold.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
        'arialbd.ttf',
    ]
    semi_paths = [
        r'C:\Windows\Fonts\seguisb.ttf',
        r'C:\Windows\Fonts\segoeuib.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'arialbd.ttf'),
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans-Bold.ttf'),
    ]
    reg_paths = [
        r'C:\Windows\Fonts\segoeui.ttf',
        r'C:\Windows\Fonts\arial.ttf',
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'arial.ttf'),
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf'),
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
        'arial.ttf',
    ]

    def pick(paths, size):
        for path in paths:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    return {
        'initial': pick(bold_paths, 150),
        'name': pick(bold_paths, 46),
        'badge': pick(bold_paths, 16),
        'sub': pick(semi_paths, 23),
        'meta': pick(reg_paths, 21),
        'meta_bold': pick(bold_paths, 21),
        'stat_num': pick(bold_paths, 40),
        'stat_lbl': pick(bold_paths, 16),
        'pill': pick(bold_paths, 19),
        'footer': pick(bold_paths, 19),
        'footer_bold': pick(bold_paths, 21),
    }


def _text_size(draw, text, font):
    if not isinstance(text, str):
        text = _safe_str(text, "")
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try:
            return draw.textsize(text, font=font)
        except Exception:
            return (len(text) * 10, 20)


def _rounded_rect(draw, box, radius, fill=None, outline=None, width=1):
    if hasattr(draw, 'rounded_rectangle'):
        draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    else:
        draw.rectangle(box, fill=fill, outline=outline, width=width)


def _cover_crop(img, w, h):
    src_w, src_h = img.size
    if src_w == 0 or src_h == 0:
        return Image.new('RGB', (w, h), (30, 58, 138))
    scale = max(w / src_w, h / src_h)
    nw, nh = max(1, int(src_w * scale)), max(1, int(src_h * scale))
    img = img.resize((nw, nh), RESAMPLE)
    left = max(0, (nw - w) // 2)
    top = max(0, (nh - h) // 2)
    return img.crop((left, top, left + w, top + h))


# Remote photos are only ever stored on Cloudinary (see fastapi profile_service
# _is_own_photo_url); anything else is not fetched server-side.
_REMOTE_PHOTO_HOSTS = {'res.cloudinary.com'}


def _fetch_remote_photo(url):
    import requests
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme != 'https' or (parsed.hostname or '').lower() not in _REMOTE_PHOTO_HOSTS:
            return None
        res = requests.get(url, timeout=5, allow_redirects=False)
        if res.status_code == 200:
            return Image.open(io.BytesIO(res.content))
    except Exception:
        pass
    return None


def _load_photo(agent, profile):
    if not profile:
        return None

    url = (getattr(profile, 'profile_photo_url', '') or '').strip()
    if url and 'avatar-icon' not in url.lower():
        if url.startswith('/media/'):
            local = os.path.join(settings.MEDIA_ROOT, url[len('/media/'):].replace('/', os.sep))
            if os.path.exists(local) and os.path.isfile(local):
                try:
                    return Image.open(local)
                except Exception:
                    pass
        elif url.startswith('/static/'):
            local = os.path.join(settings.BASE_DIR, url.lstrip('/').replace('/', os.sep))
            if os.path.exists(local) and os.path.isfile(local):
                try:
                    return Image.open(local)
                except Exception:
                    pass
        elif url.startswith(('http://', 'https://')):
            photo = _fetch_remote_photo(url)
            if photo is not None:
                return photo

    raw_path = (profile.profile_photo_path or '').strip()
    if not raw_path:
        return None
    if '?' in raw_path:
        raw_path = raw_path.split('?')[0]

    if raw_path.startswith(('http://', 'https://')):
        return _fetch_remote_photo(raw_path)

    normalized_path = raw_path.replace('\\', '/').lstrip('/')
    filename = os.path.basename(normalized_path)
    possible_paths = [
        os.path.join(settings.MEDIA_ROOT, normalized_path),
        os.path.join(settings.MEDIA_ROOT, 'app', 'public', 'profile', filename),
        os.path.join(settings.MEDIA_ROOT, 'app', 'public', normalized_path),
        os.path.join(settings.BASE_DIR, 'media', 'app', 'public', 'profile', filename),
        os.path.join(settings.BASE_DIR, 'media', normalized_path),
    ]
    for path in possible_paths:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                return Image.open(path)
            except Exception:
                continue
    return None


def _shrink_font(draw, text, font, max_w, min_size):
    """Smaller variant of font until text fits max_w (or min_size is reached)."""
    size = getattr(font, 'size', None)
    while size and size > min_size and _text_size(draw, text, font)[0] > max_w:
        size -= 2
        font = font.font_variant(size=size)
    return font


def _fit_text(draw, text, font, max_w):
    """Shorten text with an ellipsis so it never runs past max_w (server fonts are wider than dev fonts)."""
    if max_w <= 0 or _text_size(draw, text, font)[0] <= max_w:
        return text
    while text and _text_size(draw, text + '…', font)[0] > max_w:
        text = text[:-1]
    return text.rstrip() + '…'


def _draw_pin(draw, cx, cy, fill):
    """Small map-pin marker (the emoji has no glyph in the card fonts)."""
    draw.ellipse([(cx - 7, cy - 11), (cx + 7, cy + 3)], fill=fill)
    draw.polygon([(cx - 6, cy - 2), (cx + 6, cy - 2), (cx, cy + 11)], fill=fill)
    draw.ellipse([(cx - 3, cy - 7), (cx + 3, cy - 1)], fill=(255, 255, 255))


def _draw_star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
    draw.polygon(pts, fill=fill)


__all__ = ['render_agent_og_jpeg']
