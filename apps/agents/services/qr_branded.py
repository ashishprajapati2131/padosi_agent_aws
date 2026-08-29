"""
Branded PadosiAgent QR posters (profile / card / reviews).

Uses qrcode[pil] + Pillow. Images are cached so dashboard load stays cheap.
"""
import io
import logging
import os

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse

from apps.agents.services.review_growth import QR_TYPE_LABELS, QR_TYPES, is_qr_enabled
from apps.home.models import SiteSetting

logger = logging.getLogger(__name__)

POSTER_WIDTH = 1080
POSTER_HEIGHT = 1350
QR_BOX = 620
POSTER_VERSION = 'v4'


def build_qr_target_url(request, agent, qr_type):
    slug = getattr(agent, 'agent_slug', None) or str(agent.id)
    if qr_type == 'card':
        path = reverse('agents:agent_public_card', kwargs={'slug': slug})
    else:
        path = reverse('agents:agent_public_profile', kwargs={'slug': slug})
        if qr_type == 'reviews':
            path = f'{path}?focus=reviews'
    return request.build_absolute_uri(path)


def _site_name():
    return SiteSetting.get_value('site_name', 'PadosiAgent') or 'PadosiAgent'


def _logo_version():
    return str(SiteSetting.get_value('site_logo', '') or '')


def _cache_key(agent, qr_type, target_url):
    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else None
    name = (profile.display_name if profile and profile.display_name else '') or agent.fullname or ''
    slug = getattr(agent, 'agent_slug', '') or ''
    return f"agent_qr_{POSTER_VERSION}_{agent.id}_{qr_type}_{slug}_{name}_{_logo_version()}_{hash(target_url)}"


def _open_image(path):
    from PIL import Image
    if not path or not os.path.exists(path):
        return None
    try:
        return Image.open(path).convert('RGBA')
    except Exception:
        return None


def _load_brand_logo():
    from django.contrib.staticfiles import finders

    logo_setting = SiteSetting.get_value('site_logo', '') or ''
    if logo_setting:
        relative = logo_setting.replace('\\', '/')
        if relative.startswith('/media/'):
            disk = os.path.join(str(settings.MEDIA_ROOT), relative[len('/media/'):])
            img = _open_image(disk)
            if img:
                return img
        if relative.startswith('media/'):
            disk = os.path.join(str(settings.MEDIA_ROOT), relative[len('media/'):])
            img = _open_image(disk)
            if img:
                return img
        media_guess = os.path.join(str(settings.MEDIA_ROOT), relative.lstrip('/'))
        img = _open_image(media_guess)
        if img:
            return img

    for name in ('img/logo.webp', 'img/logo.png', 'img/logo-icon.webp', 'img/logo-icon.png'):
        found = finders.find(name)
        img = _open_image(found)
        if img:
            return img
        disk = os.path.join(str(settings.BASE_DIR), 'static', name.replace('/', os.sep))
        img = _open_image(disk)
        if img:
            return img
    return None


def _get_font(bold, size):
    from PIL import ImageFont

    names = (
        ['arialbd.ttf', 'Arial Bold.ttf', 'DejaVuSans-Bold.ttf']
        if bold
        else ['arial.ttf', 'Arial.ttf', 'DejaVuSans.ttf']
    )
    search = []
    fonts_dir = os.path.join(str(settings.BASE_DIR), 'static', 'fonts')
    for name in names:
        search.append(os.path.join(fonts_dir, name))
        search.append(name)
    for path in search:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(draw, text, font_fn, max_width, start_size, min_size=28):
    size = start_size
    while size >= min_size:
        font = font_fn(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 2
    return font_fn(min_size)


def _rounded_rect(draw, box, radius, fill, outline=None, width=1):
    kwargs = {'outline': outline, 'width': width}
    if fill is not None:
        kwargs['fill'] = fill
    if hasattr(draw, 'rounded_rectangle'):
        draw.rounded_rectangle(box, radius=radius, **kwargs)
    else:
        draw.rectangle(box, **kwargs)


def _make_whatsapp_mark(size):
    from PIL import Image, ImageDraw

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(37, 211, 102, 255))
    pad = int(size * 0.18)
    bubble = (pad, int(size * 0.14), size - pad, int(size * 0.68))
    _rounded_rect(draw, bubble, int(size * 0.18), fill=(255, 255, 255, 255))
    draw.polygon(
        [
            (int(size * 0.22), int(size * 0.60)),
            (int(size * 0.16), int(size * 0.86)),
            (int(size * 0.44), int(size * 0.64)),
        ],
        fill=(255, 255, 255, 255),
    )
    # Handset in brand green
    hx0, hy0 = int(size * 0.34), int(size * 0.30)
    hx1, hy1 = int(size * 0.66), int(size * 0.54)
    _rounded_rect(draw, (hx0, hy0, hx1, hy1), int(size * 0.08), fill=(37, 211, 102, 255))
    return img


def _make_instagram_mark(size):
    from PIL import Image, ImageDraw

    gradient = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / max(size - 1, 1)
        r = int(249 + (131 - 249) * t)
        g = int(168 + (58 - 168) * t)
        b = int(37 + (193 - 37) * t)
        gdraw.line((0, y, size, y), fill=(r, g, b, 255))

    mask = Image.new('L', (size, size), 0)
    _rounded_rect(ImageDraw.Draw(mask), (0, 0, size - 1, size - 1), int(size * 0.22), fill=255)
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    img.paste(gradient, (0, 0))
    img.putalpha(mask)

    draw = ImageDraw.Draw(img)
    m = int(size * 0.22)
    ring = max(2, size // 16)
    _rounded_rect(
        draw,
        (m, m, size - m, size - m),
        int(size * 0.14),
        fill=None,
        outline=(255, 255, 255, 255),
        width=ring,
    )
    cx = size // 2
    cy = int(size * 0.54)
    cr = int(size * 0.14)
    draw.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), outline=(255, 255, 255, 255), width=ring)
    dr = max(2, size // 16)
    dx, dy = int(size * 0.70), int(size * 0.32)
    draw.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=(255, 255, 255, 255))
    return img


def _make_facebook_mark(size):
    from PIL import Image, ImageDraw

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(24, 119, 242, 255))
    font = _get_font(True, int(size * 0.62))
    bbox = draw.textbbox((0, 0), 'f', font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 + size * 0.08, (size - th) / 2 - size * 0.10),
        'f',
        font=font,
        fill=(255, 255, 255, 255),
    )
    return img


def _paste_social_row(canvas, center_y, icon_size=72):
    icons = (
        _make_whatsapp_mark(icon_size),
        _make_instagram_mark(icon_size),
        _make_facebook_mark(icon_size),
    )
    gap = 28
    total = icon_size * len(icons) + gap * (len(icons) - 1)
    start_x = (POSTER_WIDTH - total) // 2
    for index, mark in enumerate(icons):
        canvas.paste(mark, (start_x + index * (icon_size + gap), center_y), mark)


def _make_qr_image(target_url, logo):
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=(15, 58, 138), back_color=(255, 255, 255)).convert('RGBA')
    qr_img = qr_img.resize((QR_BOX, QR_BOX), Image.Resampling.LANCZOS)

    if logo is not None:
        mark = logo.copy()
        mark_size = int(QR_BOX * 0.18)
        mark.thumbnail((mark_size, mark_size), Image.Resampling.LANCZOS)
        pad = 16
        badge_size = max(mark.size) + pad
        badge = Image.new('RGBA', (badge_size, badge_size), (255, 255, 255, 255))
        bx = (badge_size - mark.size[0]) // 2
        by = (badge_size - mark.size[1]) // 2
        badge.paste(mark, (bx, by), mark)
        pos = ((QR_BOX - badge_size) // 2, (QR_BOX - badge_size) // 2)
        qr_img.paste(badge, pos, badge)
    return qr_img


def generate_branded_qr_png(agent, qr_type, target_url):
    """Return PNG bytes for a branded poster, or None on failure."""
    from PIL import Image, ImageDraw

    if qr_type not in QR_TYPES:
        return None

    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else None
    agent_name = (profile.display_name if profile and getattr(profile, 'display_name', None) else '') or agent.fullname or 'Agent'
    site_name = _site_name()
    type_label = QR_TYPE_LABELS.get(qr_type, qr_type.title())
    logo = _load_brand_logo()

    canvas = Image.new('RGB', (POSTER_WIDTH, POSTER_HEIGHT), (15, 23, 42))
    draw = ImageDraw.Draw(canvas)
    header_h = 280
    for y in range(header_h):
        t = y / header_h
        r = int(30 + (15 - 30) * t)
        g = int(58 + (23 - 58) * t)
        b = int(138 + (42 - 138) * t)
        draw.line((0, y, POSTER_WIDTH, y), fill=(r, g, b))

    _rounded_rect(draw, (48, 210, POSTER_WIDTH - 48, POSTER_HEIGHT - 48), 36, fill=(255, 255, 255))

    title_font = _get_font(True, 56)
    title = site_name
    tw = draw.textbbox((0, 0), title, font=title_font)
    draw.text(((POSTER_WIDTH - (tw[2] - tw[0])) / 2, 72), title, font=title_font, fill=(255, 255, 255))

    subtitle_font = _get_font(False, 28)
    subtitle = 'Scan to connect with your neighbourhood agent'
    sw = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    draw.text(((POSTER_WIDTH - (sw[2] - sw[0])) / 2, 144), subtitle, font=subtitle_font, fill=(226, 232, 240))

    qr_img = _make_qr_image(target_url, logo)
    qr_x = (POSTER_WIDTH - QR_BOX) // 2
    qr_y = 250
    canvas.paste(qr_img, (qr_x, qr_y), qr_img)

    _paste_social_row(canvas, qr_y + QR_BOX + 24, icon_size=72)

    name_font = _fit_text(draw, agent_name, lambda s: _get_font(True, s), POSTER_WIDTH - 160, 48)
    nw = draw.textbbox((0, 0), agent_name, font=name_font)
    draw.text(((POSTER_WIDTH - (nw[2] - nw[0])) / 2, 1018), agent_name, font=name_font, fill=(15, 23, 42))

    label_font = _get_font(True, 30)
    label = type_label.upper()
    lw = draw.textbbox((0, 0), label, font=label_font)
    draw.text(((POSTER_WIDTH - (lw[2] - lw[0])) / 2, 1090), label, font=label_font, fill=(29, 125, 93))

    foot_font = _get_font(False, 26)
    foot = 'padosiagent.com'
    fw = draw.textbbox((0, 0), foot, font=foot_font)
    draw.text(((POSTER_WIDTH - (fw[2] - fw[0])) / 2, 1158), foot, font=foot_font, fill=(100, 116, 139))

    buf = io.BytesIO()
    canvas.convert('RGB').save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def get_or_create_qr_png(request, agent, qr_type):
    if qr_type not in QR_TYPES or not is_qr_enabled():
        return None
    target_url = build_qr_target_url(request, agent, qr_type)
    key = _cache_key(agent, qr_type, target_url)
    cached = cache.get(key)
    if cached:
        return cached
    try:
        png = generate_branded_qr_png(agent, qr_type, target_url)
    except Exception:
        logger.exception('Branded QR generation failed for agent %s type %s', getattr(agent, 'id', '?'), qr_type)
        return None
    if png:
        cache.set(key, png, timeout=86400)
    return png
