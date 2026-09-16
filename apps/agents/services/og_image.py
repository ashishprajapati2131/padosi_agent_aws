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
    """Return JPEG bytes for a 1200x630 agent-card style OG image."""
    width, height = 1200, 630
    canvas = Image.new('RGB', (width, height), (241, 245, 249))
    draw = ImageDraw.Draw(canvas)

    fonts = _load_fonts()
    profile = AgentProfile.objects.filter(agent=agent).first()
    perf = AgentPerformanceStat.objects.filter(agent=agent).first()

    # Main Card Box
    card = (36, 36, 1164, 594)  # 1128 x 558
    # Multi-layer soft drop shadow
    _rounded_rect(draw, (card[0] + 4, card[1] + 8, card[2] + 4, card[3] + 8), 24, fill=(203, 213, 225))
    _rounded_rect(draw, (card[0] + 2, card[1] + 4, card[2] + 2, card[3] + 4), 24, fill=(226, 232, 240))
    _rounded_rect(draw, card, 24, fill=(255, 255, 255), outline=(226, 232, 240), width=2)

    # ── Left Photo Column (370px width) ───────────────────────────────────────
    photo_w = 370
    photo_box = (card[0], card[1], card[0] + photo_w, card[3])
    x0, y0, x1, y1 = photo_box
    pw, ph = x1 - x0, y1 - y0

    src = _load_photo(agent, profile)
    if src is not None:
        try:
            if src.mode not in ('RGB', 'RGBA'):
                src = src.convert('RGB')
            fitted = _cover_crop(src.convert('RGB'), pw, ph)
        except Exception:
            fitted = None
    else:
        fitted = None

    if fitted is None:
        # Elegant royal blue fallback avatar
        fitted = Image.new('RGB', (pw, ph), (26, 54, 124))
        d = ImageDraw.Draw(fitted)
        name_str = ((profile.display_name if profile else '') or agent.fullname or 'A').strip()
        words = [w for w in name_str.split() if w]
        initial = ''.join([w[0].upper() for w in words[:2]]) or 'A'
        
        # Draw circular ring
        cx, cy = pw // 2, (ph // 2) - 25
        cr = 65
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(37, 72, 160), outline=(255, 255, 255), width=3)
        tw, th = _text_size(d, initial, fonts['name'])
        d.text((cx - tw / 2, cy - th / 2 - 4), initial, font=fonts['name'], fill=(255, 255, 255))

        init_sub = "Verified Insurance Advisor"
        sw, _ = _text_size(d, init_sub, fonts['pill'])
        d.text(((pw - sw) / 2, cy + cr + 22), init_sub, font=fonts['pill'], fill=(219, 234, 254))

    # Add dark gradient overlay to bottom of photo for text legibility
    gradient_h = 130
    overlay = Image.new('RGBA', (pw, gradient_h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for row in range(gradient_h):
        alpha = int(210 * (row / gradient_h) ** 1.3)
        od.line([(0, row), (pw, row)], fill=(15, 23, 42, alpha))
    fitted.paste(overlay, (0, ph - gradient_h), mask=overlay)

    # Location / City badge on photo bottom
    fd = ImageDraw.Draw(fitted)
    city_text = (getattr(agent, 'agent_city_display', '') or getattr(profile, 'city', '') or 'India').strip()
    if '+' in city_text:
        city_text = city_text.split('+')[0].strip()
    loc_label = f"{city_text}"
    ltw, _ = _text_size(fd, loc_label, fonts['loc'])
    pill_x = 24
    pill_y = ph - 54
    pill_w = ltw + 34
    pill_h = 32
    _rounded_rect(fd, (pill_x, pill_y, pill_x + pill_w, pill_y + pill_h), 16, fill=(15, 23, 42), outline=(51, 65, 85), width=1)
    fd.text((pill_x + 14, pill_y + 6), loc_label, font=fonts['loc'], fill=(255, 255, 255))

    # Paste photo with left-rounded mask
    mask = Image.new('L', (pw, ph), 0)
    md = ImageDraw.Draw(mask)
    _rounded_rect(md, (0, 0, pw, ph), 24, fill=255)
    md.rectangle((pw - 30, 0, pw, ph), fill=255)  # sharp on right side
    canvas.paste(fitted, (x0, y0), mask=mask)

    # Vertical divider
    draw.line([(x1, y0), (x1, y1)], fill=(226, 232, 240), width=1)

    # ── Right Content Area ───────────────────────────────────────────────────
    content_x = x1 + 36
    content_right = card[2] - 36
    y = card[1] + 28

    # Top Header: PadosiAgent Logo & Brand
    brand_logo_path = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo.png')
    logo_drawn = False
    if os.path.exists(brand_logo_path):
        try:
            logo_img = Image.open(brand_logo_path)
            lh = 28
            lw = int(logo_img.width * (lh / logo_img.height))
            logo_resized = logo_img.resize((lw, lh), RESAMPLE)
            if logo_resized.mode == 'RGBA':
                canvas.paste(logo_resized, (content_x, y), mask=logo_resized)
            else:
                canvas.paste(logo_resized, (content_x, y))
            logo_drawn = True
        except Exception:
            pass

    if not logo_drawn:
        draw.text((content_x, y), "PADOSIAGENT", font=fonts['brand'], fill=(30, 58, 138))
        draw.text((content_x + 175, y + 5), "· Trusted Insurance Network", font=fonts['brand_sub'], fill=(100, 116, 139))

    # Top Right Header Pill: Verified Advisor
    verified_text = "Verified Advisor"
    vw, _ = _text_size(draw, verified_text, fonts['pill'])
    vx = content_right - (vw + 32)
    _rounded_rect(draw, (vx, y - 2, content_right, y + 28), 15, fill=(240, 253, 244), outline=(187, 247, 208), width=1)
    draw.text((vx + 16, y + 3), verified_text, font=fonts['pill'], fill=(22, 101, 52))

    y += 52

    # Agent Display Name
    display_name = ((profile.display_name if profile else '') or agent.fullname or 'Insurance Advisor').strip()
    name_font = fonts['name_sm'] if len(display_name) > 22 else fonts['name']
    draw.text((content_x, y), display_name, font=name_font, fill=(15, 23, 42))

    # Badges row (Licensed, Trusted) beside name or next row
    nw, nh = _text_size(draw, display_name, name_font)
    badge_x = content_x + nw + 16
    badge_y = y + 8
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
    )

    badges = []
    if show_licensed:
        badges.append(('IRDAI Licensed', (239, 246, 255), (29, 78, 216), (191, 219, 254)))
    if show_trusted:
        badges.append(('Trusted Partner', (240, 253, 244), (22, 101, 52), (187, 247, 208)))

    if badge_x + 230 > content_right:
        y += nh + 6
        badge_x = content_x
        badge_y = y

    for label, bg, fg, border in badges:
        bw, _ = _text_size(draw, label, fonts['pill'])
        pill_w = bw + 24
        _rounded_rect(draw, (badge_x, badge_y, badge_x + pill_w, badge_y + 26), 13, fill=bg, outline=border, width=1)
        draw.text((badge_x + 12, badge_y + 4), label, font=fonts['pill'], fill=fg)
        badge_x += pill_w + 10

    y += 48

    # Subtitle: Agency or Professional Title
    agency = (getattr(profile, 'agency_name', '') or '').strip()
    if agency:
        sub_text = f"Insurance & Financial Advisor · {agency}"
    else:
        sub_text = "Licensed Insurance & Financial Planning Advisor"
    draw.text((content_x, y), sub_text, font=fonts['agency'], fill=(71, 85, 105))
    y += 34

    # Stars & Rating Bar
    rating = float(getattr(agent, 'average_rating', 5.0) or 5.0)
    if rating <= 0:
        rating = 5.0
    review_count = int(getattr(agent, 'review_count', 0) or 0)
    full_stars = int(round(rating))
    full_stars = max(1, min(5, full_stars))

    for i in range(5):
        cx = content_x + 12 + i * 26
        _draw_star(draw, cx, y + 10, 11, (245, 158, 11) if i < full_stars else (226, 232, 240))

    rating_str = f"{rating:.1f}"
    rx = content_x + 142
    draw.text((rx, y), rating_str, font=fonts['rating'], fill=(15, 23, 42))
    rw = _text_size(draw, rating_str, fonts['rating'])[0]
    count_label = f"({review_count} Verified Reviews)" if review_count else "(Verified Partner Rating)"
    draw.text((rx + rw + 10, y + 3), count_label, font=fonts['reviews'], fill=(100, 116, 139))

    y += 46

    # Metric Boxes (4 cards)
    exp = 0
    if profile and profile.experience_years:
        exp = profile.experience_years
    else:
        exp = getattr(agent, 'experience_years', 0) or 0
    clients = getattr(agent, 'formatted_client_base', None) or str(getattr(agent, 'client_base', '') or '0')
    claims = perf.formatted_claims_processed if perf else '0'
    settled = perf.formatted_claims_amount if perf else '0'

    metrics = [
        (f"{exp}+" if exp else "1+", "YEARS EXP"),
        (str(clients or "50+"), "CLIENTS"),
        (str(claims or "10+"), "CLAIMS"),
        (f"₹{settled}" if settled and settled != '0' else "₹10L+", "SETTLED"),
    ]

    gap = 14
    count = len(metrics)
    box_w = int((content_right - content_x - gap * (count - 1)) / count)
    box_h = 92

    for i, (value, label) in enumerate(metrics):
        bx = content_x + i * (box_w + gap)
        _rounded_rect(draw, (bx, y, bx + box_w, y + box_h), 14, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
        vw, _ = _text_size(draw, value, fonts['val'])
        lw, _ = _text_size(draw, label, fonts['label'])
        draw.text((bx + (box_w - vw) / 2, y + 16), value, font=fonts['val'], fill=(15, 23, 42))
        draw.text((bx + (box_w - lw) / 2, y + 54), label, font=fonts['label'], fill=(100, 116, 139))

    y += box_h + 20

    # Service Tags (Health, Life, Motor, SME)
    tags = list(getattr(agent, 'ordered_insurance_segments', None) or [])
    if not tags:
        tags = ['health', 'life', 'motor']
    cursor = content_x
    for raw in tags[:4]:
        key = str(raw or '').strip().lower()
        if not key:
            continue
        label = f"{key.upper() if key == 'sme' else key.capitalize()} Insurance"
        bg, fg, border = TAG_COLORS.get(key, TAG_DEFAULT)
        tw, _ = _text_size(draw, label, fonts['tag'])
        bw = tw + 26
        _rounded_rect(draw, (cursor, y, cursor + bw, y + 32), 16, fill=bg, outline=border, width=1)
        draw.text((cursor + 13, y + 6), label, font=fonts['tag'], fill=fg)
        cursor += bw + 10

    # Bottom Footer Strip
    footer_y = card[3] - 42
    draw.line([(content_x, footer_y - 12), (content_right, footer_y - 12)], fill=(241, 245, 249), width=1)

    cta_text = "Instant Policy Assistance · Claim Support · Free Consultation"
    draw.text((content_x, footer_y), cta_text, font=fonts['cta'], fill=(100, 116, 139))

    domain_text = "padosiagent.com"
    dw, _ = _text_size(draw, domain_text, fonts['cta'])
    draw.text((content_right - dw, footer_y), domain_text, font=fonts['cta'], fill=(30, 58, 138))

    buf = io.BytesIO()
    canvas.save(buf, format='JPEG', quality=93)
    return buf.getvalue()


def _load_fonts():
    bold_paths = [
        r'C:\Windows\Fonts\segoeuib.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'arialbd.ttf'),
        'arialbd.ttf',
    ]
    semi_paths = [
        r'C:\Windows\Fonts\seguisb.ttf',
        r'C:\Windows\Fonts\segoeuib.ttf',
        r'C:\Windows\Fonts\arialbd.ttf',
    ]
    reg_paths = [
        r'C:\Windows\Fonts\segoeui.ttf',
        r'C:\Windows\Fonts\arial.ttf',
        os.path.join(settings.BASE_DIR, 'static', 'fonts', 'arial.ttf'),
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
