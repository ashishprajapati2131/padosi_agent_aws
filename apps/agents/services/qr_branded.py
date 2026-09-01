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
POSTER_HEIGHT = 1440
QR_BOX = 580
POSTER_VERSION = 'v9'
SOCIAL_ICON_SIZE = 72
CARD_MARGIN = 0
CARD_RADIUS = 32

BRAND_NAVY = (30, 64, 175)
BRAND_BLUE = (24, 82, 157)
BRAND_TEAL = (15, 118, 110)
BRAND_GREEN = (29, 125, 93)
BRAND_GOLD = (245, 158, 11)
QR_FILL = (0, 0, 0)
BRAND_SLATE = (15, 23, 42)
CORNER_COLORS = (BRAND_BLUE, BRAND_TEAL, BRAND_GOLD, BRAND_GREEN)
SOCIAL_COLORS = {
    'whatsapp': (37, 211, 102),
    'instagram': (225, 48, 108),
    'facebook': (24, 119, 242),
}

TYPE_COPY = {
    'profile': {
        'headline': 'View my agent profile',
        'subline': 'Scan to connect with your neighbourhood insurance advisor',
        'cta': 'Trusted agent on PadosiAgent — India\'s agent network',
    },
    'card': {
        'headline': 'My digital business card',
        'subline': 'Scan to save my contact, services & details instantly',
        'cta': 'Professional · Shareable · Always up to date',
    },
    'reviews': {
        'headline': 'Leave a review & rating',
        'subline': 'Scan to share your experience and help others choose wisely',
        'cta': 'Your feedback builds trust in our community',
    },
}


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


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _draw_centered_text(draw, y, text, font, fill, canvas_width=POSTER_WIDTH):
    tw = _text_width(draw, text, font)
    draw.text(((canvas_width - tw) / 2, y), text, font=font, fill=fill)


def _draw_card_corner_accents(draw, box, arm=72, width=10):
    """PVC-style coloured L-corners (top-left → clockwise)."""
    x0, y0, x1, y1 = box
    corners = (
        ((x0, y0 + arm, x0, y0, x0 + arm, y0), CORNER_COLORS[0]),
        ((x1 - arm, y0, x1, y0, x1, y0 + arm), CORNER_COLORS[1]),
        ((x1, y1 - arm, x1, y1, x1 - arm, y1), CORNER_COLORS[2]),
        ((x0 + arm, y1, x0, y1, x0, y1 - arm), CORNER_COLORS[3]),
    )
    for points, color in corners:
        draw.line(points, fill=color, width=width, joint='curve')


def _draw_qr_scan_frame(draw, x, y, size, arm=56, width=9):
    """Coloured scan brackets around the QR (reference-style)."""
    colors = CORNER_COLORS
    frames = (
        ((x, y + arm, x, y, x + arm, y), colors[0]),
        ((x + size - arm, y, x + size, y, x + size, y + arm), colors[1]),
        ((x + size, y + size - arm, x + size, y + size, x + size - arm, y + size), colors[2]),
        ((x + arm, y + size, x, y + size, x, y + size - arm), colors[3]),
    )
    for points, color in frames:
        draw.line(points, fill=color, width=width, joint='curve')


def _draw_star_row(draw, center_x, y, size=34, gap=8):
    """Five gold stars for review/trust cue."""
    total_w = size * 5 + gap * 4
    start_x = center_x - total_w // 2
    star_font = _get_font(False, size)
    for i in range(5):
        draw.text((start_x + i * (size + gap), y), '\u2605', font=star_font, fill=BRAND_GOLD)


def _paste_header_logo(canvas, logo, top_y):
    if logo is None:
        return top_y
    from PIL import Image

    mark = logo.copy()
    max_w = 200
    mark.thumbnail((max_w, max_w), Image.Resampling.LANCZOS)
    x = (POSTER_WIDTH - mark.size[0]) // 2
    canvas.paste(mark, (x, top_y), mark)
    return top_y + mark.size[1] + 18


def _social_svg_path(name):
    from django.contrib.staticfiles import finders
    rel = f'img/social/{name}.svg'
    found = finders.find(rel)
    if found and os.path.isfile(found):
        return found
    disk = os.path.join(str(settings.BASE_DIR), 'static', 'img', 'social', f'{name}.svg')
    return disk if os.path.isfile(disk) else None


def _glyph_from_svg(name, size):
    """Load a white glyph PNG (bundled) or rasterize SVG when possible."""
    from PIL import Image, ImageDraw

    svg_path = _social_svg_path(name)
    if svg_path:
        glyph_png = svg_path.replace('.svg', '-glyph.png')
        if os.path.isfile(glyph_png):
            try:
                img = Image.open(glyph_png).convert('RGBA')
                if img.size != (size, size):
                    img = img.resize((size, size), Image.Resampling.LANCZOS)
                return img
            except Exception:
                pass
    if not svg_path:
        return None
    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(url=svg_path, output_width=size, output_height=size)
        return Image.open(io.BytesIO(png_bytes)).convert('RGBA')
    except Exception:
        pass
    try:
        import xml.etree.ElementTree as ET
        from svg.path import parse_path

        tree = ET.parse(svg_path)
        root = tree.getroot()
        paths = root.findall('.//{http://www.w3.org/2000/svg}path')
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        all_pts = []
        for path_el in paths:
            d = path_el.get('d')
            if not d:
                continue
            path = parse_path(d)
            for seg in path:
                steps = 12
                try:
                    steps = max(4, min(24, int(seg.length() * 2)))
                except Exception:
                    pass
                for i in range(steps + 1):
                    pt = seg.point(i / steps)
                    all_pts.append((pt.real, pt.imag))
        if not all_pts:
            return None
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        pad = 6
        scale = (size - 2 * pad) / max(maxx - minx, maxy - miny, 1)
        norm = [((x - minx) * scale + pad, (y - miny) * scale + pad) for x, y in all_pts]
        draw.polygon(norm, fill=(255, 255, 255, 255))
        return img
    except Exception:
        return None


def _brand_social_icon(name, size):
    """Circle badge with official-style white glyph."""
    from PIL import Image, ImageDraw

    color = SOCIAL_COLORS.get(name, (100, 116, 139))
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(*color, 255))

    if name == 'instagram':
        gradient = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(gradient)
        for y in range(size):
            t = y / max(size - 1, 1)
            r = int(249 + (131 - 249) * t)
            g = int(168 + (58 - 168) * t)
            b = int(37 + (193 - 37) * t)
            gdraw.line((0, y, size, y), fill=(r, g, b, 255))
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        img.paste(gradient, (0, 0))
        img.putalpha(mask)

    glyph_size = int(size * 0.54)
    glyph = _glyph_from_svg(name, glyph_size)
    if glyph is None:
        if name == 'whatsapp':
            return _make_whatsapp_mark_fallback(size)
        if name == 'instagram':
            return _make_instagram_mark_fallback(size)
        if name == 'facebook':
            return _make_facebook_mark_fallback(size)
        return img

    ox = (size - glyph.width) // 2
    oy = (size - glyph.height) // 2
    img.paste(glyph, (ox, oy), glyph)
    return img


def _make_whatsapp_mark_fallback(size):
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(37, 211, 102, 255))
    pad = int(size * 0.22)
    bubble = (pad, int(size * 0.18), size - pad, int(size * 0.62))
    _rounded_rect(draw, bubble, int(size * 0.16), fill=(255, 255, 255, 255))
    tail = [
        (int(size * 0.24), int(size * 0.58)),
        (int(size * 0.18), int(size * 0.78)),
        (int(size * 0.42), int(size * 0.62)),
    ]
    draw.polygon(tail, fill=(255, 255, 255, 255))
    rx0, ry0 = int(size * 0.38), int(size * 0.32)
    rx1, ry1 = int(size * 0.62), int(size * 0.52)
    _rounded_rect(draw, (rx0, ry0, rx1, ry1), int(size * 0.06), fill=(37, 211, 102, 255))
    return img


def _make_instagram_mark_fallback(size):
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


def _make_facebook_mark_fallback(size):
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


def _paste_social_row(canvas, center_y, icon_size=None):
    if icon_size is None:
        icon_size = SOCIAL_ICON_SIZE
    names = ('whatsapp', 'instagram', 'facebook')
    icons = [_brand_social_icon(name, icon_size) for name in names]
    gap = 32
    total = icon_size * len(icons) + gap * (len(icons) - 1)
    start_x = (POSTER_WIDTH - total) // 2
    for index, mark in enumerate(icons):
        canvas.paste(mark, (start_x + index * (icon_size + gap), center_y), mark)


def _make_qr_image(target_url):
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=QR_FILL, back_color=(255, 255, 255)).convert('RGBA')
    return qr_img.resize((QR_BOX, QR_BOX), Image.Resampling.LANCZOS)


def generate_branded_qr_png(agent, qr_type, target_url):
    """Return PNG bytes for a single PVC-style marketing card."""
    from PIL import Image, ImageDraw

    if qr_type not in QR_TYPES:
        return None

    profile = agent.get_primary_profile() if hasattr(agent, 'get_primary_profile') else None
    agent_name = (profile.display_name if profile and getattr(profile, 'display_name', None) else '') or agent.fullname or 'Agent'
    site_name = _site_name()
    type_label = QR_TYPE_LABELS.get(qr_type, qr_type.title())
    copy = TYPE_COPY.get(qr_type, TYPE_COPY['profile'])
    logo = _load_brand_logo()

    canvas = Image.new('RGB', (POSTER_WIDTH, POSTER_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    card_box = (0, 0, POSTER_WIDTH - 1, POSTER_HEIGHT - 1)
    _draw_card_corner_accents(draw, card_box, arm=80, width=11)

    y = 44
    y = _paste_header_logo(canvas, logo, y)
    if logo is None:
        brand_font = _get_font(True, 46)
        _draw_centered_text(draw, y, site_name, brand_font, BRAND_NAVY)
        y += 58

    tag_font = _get_font(False, 22)
    _draw_centered_text(draw, y, 'India\'s trusted insurance agent network', tag_font, (100, 116, 139))
    y += 40

    headline_font = _get_font(True, 38)
    _draw_centered_text(draw, y, copy['headline'], headline_font, BRAND_SLATE)
    y += 50

    name_font = _fit_text(draw, agent_name, lambda s: _get_font(True, s), POSTER_WIDTH - 160, 42, min_size=30)
    _draw_centered_text(draw, y, agent_name, name_font, BRAND_BLUE)
    y += 52

    sub_font = _get_font(False, 24)
    sub_lines = _wrap_copy(copy['subline'], 42)
    for line in sub_lines:
        _draw_centered_text(draw, y, line, sub_font, (71, 85, 105))
        y += 32

    qr_img = _make_qr_image(target_url)
    qr_x = (POSTER_WIDTH - QR_BOX) // 2
    qr_y = y + 16
    canvas.paste(qr_img, (qr_x, qr_y), qr_img)
    _draw_qr_scan_frame(draw, qr_x - 6, qr_y - 6, QR_BOX + 12, arm=52, width=8)

    y = qr_y + QR_BOX + 28
    _draw_star_row(draw, POSTER_WIDTH // 2, y, size=36, gap=10)
    y += 52

    cta_font = _get_font(False, 23)
    for line in _wrap_copy(copy['cta'], 44):
        _draw_centered_text(draw, y, line, cta_font, (51, 65, 85))
        y += 30

    y += 12
    share_font = _get_font(True, 20)
    _draw_centered_text(draw, y, 'Share on', share_font, (100, 116, 139))
    _paste_social_row(canvas, y + 30, icon_size=SOCIAL_ICON_SIZE)
    y += 30 + SOCIAL_ICON_SIZE + 28

    pill_font = _get_font(True, 22)
    pill = type_label.upper()
    pw = _text_width(draw, pill, pill_font)
    pill_w = pw + 40
    pill_h = 36
    pill_x = (POSTER_WIDTH - pill_w) // 2
    _rounded_rect(draw, (pill_x, y, pill_x + pill_w, y + pill_h), 18, fill=BRAND_TEAL)
    draw.text((pill_x + 20, y + 6), pill, font=pill_font, fill=(255, 255, 255))

    foot_font = _get_font(True, 26)
    _draw_centered_text(draw, POSTER_HEIGHT - 44, 'padosiagent.com', foot_font, BRAND_NAVY)

    buf = io.BytesIO()
    canvas.convert('RGB').save(buf, format='PNG', optimize=True)
    return buf.getvalue()


def _wrap_copy(text, max_chars):
    words = text.split()
    lines = []
    current = []
    for word in words:
        trial = ' '.join(current + [word])
        if len(trial) <= max_chars:
            current.append(word)
        else:
            if current:
                lines.append(' '.join(current))
            current = [word]
    if current:
        lines.append(' '.join(current))
    return lines or [text]


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
