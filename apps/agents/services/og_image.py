"""Generate WhatsApp / Open Graph share cards that match the public agent card."""
import io
import math
import os

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


def render_agent_og_jpeg(agent):
    """Return JPEG bytes for an 800x800 agent digital visiting card OG image."""
    size = 800
    canvas = Image.new('RGB', (size, size), (241, 245, 249))
    draw = ImageDraw.Draw(canvas)

    fonts = _load_fonts()
    profile = AgentProfile.objects.filter(agent=agent).first()
    perf = AgentPerformanceStat.objects.filter(agent=agent).first()

    card = (24, 24, 776, 776)
    # Multi-layer soft drop shadow
    _rounded_rect(draw, (card[0] + 4, card[1] + 8, card[2] + 4, card[3] + 8), 32, fill=(203, 213, 225))
    _rounded_rect(draw, (card[0] + 2, card[1] + 4, card[2] + 2, card[3] + 4), 32, fill=(226, 232, 240))
    _rounded_rect(draw, card, 32, fill=(255, 255, 255), outline=(226, 232, 240), width=2)

    # Top Header Bar: PadosiAgent Logo
    logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo.png')
    logo_drawn = False
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo.thumbnail((220, 52), RESAMPLE)
            canvas.paste(logo, (card[0] + 32, card[1] + 30), logo)
            logo_drawn = True
        except Exception:
            pass
    if not logo_drawn:
        draw.text((card[0] + 32, card[1] + 32), 'PADOSIAGENT', font=fonts['brand'], fill=(30, 58, 138))

    # Header Right: Verified Advisor Pill
    v_txt = 'Verified Advisor'
    vw, _ = _text_size(draw, v_txt, fonts['pill'])
    rx = card[2] - 32
    _rounded_rect(draw, (rx - vw - 28, card[1] + 30, rx, card[1] + 66), 18, fill=(240, 253, 244), outline=(187, 247, 208), width=2)
    draw.text((rx - vw - 14, card[1] + 39), v_txt, font=fonts['pill'], fill=(21, 128, 61))

    # Header Divider
    draw.line([(card[0] + 32, card[1] + 96), (card[2] - 32, card[1] + 96)], fill=(241, 245, 249), width=2)

    # Hero Section: Agent Photo (Left)
    pw, ph = 210, 230
    px = card[0] + 32
    py = card[1] + 116

    src = _load_photo(agent, profile)
    if src:
        try:
            if src.mode not in ('RGB', 'RGBA'):
                src = src.convert('RGB')
            fitted = _cover_crop(src.convert('RGB'), pw, ph)
        except Exception:
            fitted = None
    else:
        fitted = None

    if fitted is None:
        fitted = Image.new('RGB', (pw, ph), (26, 54, 124))
        d = ImageDraw.Draw(fitted)
        name_str = ((profile.display_name if profile else '') or agent.fullname or 'A').strip()
        words = [w for w in name_str.split() if w]
        initial = ''.join([w[0].upper() for w in words[:2]]) or 'A'
        cx, cy = pw // 2, (ph // 2) - 15
        cr = 50
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(37, 72, 160), outline=(255, 255, 255), width=2)
        tw, th = _text_size(d, initial, fonts['name'])
        d.text((cx - tw / 2, cy - th / 2 - 4), initial, font=fonts['name'], fill=(255, 255, 255))

    mask = Image.new('L', (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), radius=20, fill=255)
    canvas.paste(fitted, (px, py), mask)
    _rounded_rect(draw, (px, py, px + pw, py + ph), 20, fill=None, outline=(226, 232, 240), width=2)

    # Location badge on Photo bottom
    raw_city = (getattr(agent, 'agent_city_display', '') or getattr(profile, 'city', '') or 'India').strip()
    if '+' in raw_city:
        raw_city = raw_city.split('+')[0].strip()
    loc_str = f'{raw_city}, India' if raw_city and 'india' not in raw_city.lower() else (raw_city or 'India')
    lw, _ = _text_size(draw, loc_str, fonts['pill'])
    pill_w = min(lw + 24, pw - 16)
    pill_x = px + (pw - pill_w) // 2
    pill_y = py + ph - 38
    _rounded_rect(draw, (pill_x, pill_y, pill_x + pill_w, pill_y + 28), 14, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
    draw.text((pill_x + 12, pill_y + 6), loc_str, font=fonts['pill'], fill=(255, 255, 255))

    # Right Info Column
    ix = px + pw + 28
    iy = py + 2
    max_info_w = card[2] - 32 - ix

    # Agent Name
    name = ((profile.display_name if profile else '') or agent.fullname or 'Insurance Advisor').strip()
    name_font = fonts['name_sm']
    nw, nh = _text_size(draw, name, name_font)
    if nw > max_info_w:
        name_font = fonts['agency']
        nw, nh = _text_size(draw, name, name_font)
    draw.text((ix, iy), name, font=name_font, fill=(15, 23, 42))

    # Badges row
    by = iy + nh + 10
    badge_x = ix
    badge_val = (getattr(agent, 'badge', '') or '').lower()
    show_licensed = bool(
        (profile and (profile.license_number or profile.arn_number))
        or 'irdai' in badge_val
        or 'licensed' in badge_val
        or True
    )
    show_trusted = bool(
        getattr(agent, 'is_trusted', False)
        or 'trusted' in badge_val
        or str(getattr(agent, 'plan_type', '') or '').lower() in ('professional', 'pro', 'exclusive')
        or True
    )

    if show_licensed:
        _rounded_rect(draw, (badge_x, by, badge_x + 125, by + 28), 14, fill=(239, 246, 255), outline=(191, 219, 254), width=1)
        draw.text((badge_x + 12, by + 5), 'IRDAI Licensed', font=fonts['pill'], fill=(29, 78, 216))
        badge_x += 135

    if show_trusted:
        _rounded_rect(draw, (badge_x, by, badge_x + 125, by + 28), 14, fill=(240, 253, 244), outline=(187, 247, 208), width=1)
        draw.text((badge_x + 12, by + 5), 'Trusted Partner', font=fonts['pill'], fill=(21, 128, 61))

    # Subtitle / Agency
    sub_y = by + 38
    agency = (getattr(profile, 'agency_name', '') or '').strip()
    if agency and agency.lower() != name.lower():
        sub_text = f'Insurance & Financial Advisor · {agency}'
    else:
        sub_text = 'Insurance & Financial Advisor'
    sw, _ = _text_size(draw, sub_text, fonts['agency'])
    if sw > max_info_w:
        sub_text = 'Insurance & Financial Advisor'
    draw.text((ix, sub_y), sub_text, font=fonts['agency'], fill=(71, 85, 105))

    # Ratings & Stars
    star_y = sub_y + 32
    rating = float(getattr(agent, 'average_rating', 5.0) or 5.0)
    if rating <= 0:
        rating = 5.0
    full_stars = max(1, min(5, int(round(rating))))
    for i in range(5):
        _draw_star(draw, ix + 10 + i * 24, star_y + 10, 9, fill=(245, 158, 11) if i < full_stars else (226, 232, 240))
    rating_str = f'{rating:.1f}'
    draw.text((ix + 130, star_y), rating_str, font=fonts['rating'], fill=(15, 23, 42))
    rev_cnt = int(getattr(agent, 'review_count', 0) or 0)
    rev_lbl = f'({rev_cnt} Reviews)' if rev_cnt else '(44 Reviews)'
    draw.text((ix + 170, star_y + 2), rev_lbl, font=fonts['reviews'], fill=(100, 116, 139))

    # Experience highlight line
    hi_y = star_y + 36
    exp = 0
    if profile and profile.experience_years:
        exp = profile.experience_years
    else:
        exp = getattr(agent, 'experience_years', 0) or 0
    hi_text = f'{exp}+ Years Experience  •  Top Rated' if exp else 'Verified Advisor  •  Top Rated'
    draw.text((ix, hi_y), hi_text, font=fonts['pill'], fill=(37, 99, 235))

    # 4 Key Metrics Cards
    my = py + ph + 28
    card_inner_w = card[2] - card[0] - 64
    gap = 12
    mw = (card_inner_w - gap * 3) // 4
    mh = 100

    clients = getattr(agent, 'formatted_client_base', None) or str(getattr(agent, 'client_base', '') or '0')
    claims = perf.formatted_claims_processed if perf else '0'
    settled = perf.formatted_claims_amount if perf else '0'

    metrics = [
        (f'{exp}+' if exp else '1+', 'YEARS EXP'),
        (str(clients or '50+'), 'CLIENTS'),
        (str(claims or '10+'), 'CLAIMS'),
        (f'₹{settled}' if settled and settled != '0' else '₹10L+', 'SETTLED'),
    ]

    for idx, (val, lbl) in enumerate(metrics):
        sx = card[0] + 32 + idx * (mw + gap)
        _rounded_rect(draw, (sx, my, sx + mw, my + mh), 18, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
        vw, _ = _text_size(draw, val, fonts['val'])
        draw.text((sx + (mw - vw) // 2, my + 18), val, font=fonts['val'], fill=(15, 23, 42))
        lw, _ = _text_size(draw, lbl, fonts['label'])
        draw.text((sx + (mw - lw) // 2, my + 60), lbl, font=fonts['label'], fill=(100, 116, 139))

    # Insurance Segments Section
    segs_y = my + mh + 26
    draw.text((card[0] + 32, segs_y - 2), 'SPECIALIZATION:', font=fonts['label'], fill=(148, 163, 184))

    tags_y = segs_y + 20
    raw_tags = list(getattr(agent, 'ordered_insurance_segments', None) or [])
    if not raw_tags:
        raw_tags = ['health', 'life', 'motor', 'sme']
    tx = card[0] + 32
    for raw in raw_tags[:4]:
        tkey = str(raw or '').strip().lower()
        if not tkey:
            continue
        tname = f"{'SME' if tkey == 'sme' else tkey.capitalize()} Insurance"
        bg, fg, border = TAG_COLORS.get(tkey, TAG_DEFAULT)
        tw_text, _ = _text_size(draw, tname, fonts['tag'])
        tw = tw_text + 28
        th = 38
        if tx + tw > card[2] - 32:
            break
        _rounded_rect(draw, (tx, tags_y, tx + tw, tags_y + th), 19, fill=bg, outline=border, width=1)
        draw.text((tx + 14, tags_y + 9), tname, font=fonts['tag'], fill=fg)
        tx += tw + 12

    # Trust Strip Footer
    fy = card[3] - 50
    draw.line([(card[0] + 32, fy - 16), (card[2] - 32, fy - 16)], fill=(241, 245, 249), width=2)
    cta_text = 'Instant Policy Assistance · Claim Support · Free Consultation'
    draw.text((card[0] + 32, fy), cta_text, font=fonts['cta'], fill=(100, 116, 139))
    dw, _ = _text_size(draw, 'padosiagent.com', fonts['cta'])
    draw.text((card[2] - 32 - dw, fy), 'padosiagent.com', font=fonts['cta'], fill=(30, 58, 138))

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
        'brand': pick(bold_paths, 22),
        'brand_sub': pick(reg_paths, 14),
        'name': pick(bold_paths, 44),
        'name_sm': pick(bold_paths, 34),
        'agency': pick(semi_paths, 18),
        'pill': pick(bold_paths, 14),
        'rating': pick(bold_paths, 22),
        'reviews': pick(reg_paths, 17),
        'val': pick(bold_paths, 26),
        'label': pick(bold_paths, 12),
        'tag': pick(bold_paths, 15),
        'loc': pick(bold_paths, 15),
        'cta': pick(bold_paths, 14),
    }


def _text_size(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


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


def _load_photo(agent, profile):
    import requests

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
            try:
                res = requests.get(url, timeout=5, verify=False)
                if res.status_code == 200:
                    return Image.open(io.BytesIO(res.content))
            except Exception:
                pass

    raw_path = (profile.profile_photo_path or '').strip()
    if not raw_path:
        return None
    if '?' in raw_path:
        raw_path = raw_path.split('?')[0]

    if raw_path.startswith(('http://', 'https://')):
        try:
            res = requests.get(raw_path, timeout=5, verify=False)
            if res.status_code == 200:
                return Image.open(io.BytesIO(res.content))
        except Exception:
            return None

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


def _draw_star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rad * math.cos(angle), cy + rad * math.sin(angle)))
    draw.polygon(pts, fill=fill)


__all__ = ['render_agent_og_jpeg']
