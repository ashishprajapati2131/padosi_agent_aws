"""Festive layout of the 1200x630 agent share card (theme share_layout = 'festive').

A framed card floats over a blurred copy of the theme artwork: PadosiAgent brand
panel on the left, the agent's details on a cream panel, colour-coded stat cards,
the theme greeting between two decorations (e.g. diyas) and a purple footer bar.
Every agent value comes from og_image._card_data (what the agent saved and chose
to show); nothing is hard-coded. Drawn with Pillow only, like the classic card.
"""

import io
import os

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from apps.agents.services.og_image import (
    PILL_COLORS,
    RESAMPLE,
    _card_data,
    _cover_crop,
    _draw_pin,
    _draw_star,
    _fit_text,
    _hex_rgb,
    _load_card_sources,
    _load_photo,
    _shrink_font,
    _text_size,
    _wrap_lines,
)

W, H = 1200, 630
CARD = (8, 8, 1192, 622)  # gold frame just inside the full-bleed image
INFO = (372, 32, 1164, 516)  # cream info panel
X0 = 400  # left edge of the agent details
STAT_ROW = (192, 310)
NAVY, GOLD, ORANGE = (30, 27, 75), (233, 185, 73), (234, 88, 12)
STAT_STYLE = {  # label -> (fill, border, icon colour, icon)
    "YEARS EXP": ((232, 241, 254), (188, 212, 246), (37, 99, 235), "calendar"),
    "CLIENTS": ((241, 236, 253), (214, 200, 247), (124, 58, 237), "people"),
    "CLAIMS": ((253, 238, 243), (245, 198, 214), (219, 39, 119), "document"),
    "SETTLED": ((233, 249, 238), (191, 232, 204), (22, 163, 74), "coins"),
}


def _font(bold, size):
    names = (
        ["arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["arial.ttf", "DejaVuSans.ttf"]
    )
    for name in names:
        for path in (os.path.join(settings.BASE_DIR, "static", "fonts", name), name):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _symbol_font(size):
    try:
        return ImageFont.truetype(
            os.path.join(settings.BASE_DIR, "static", "fonts", "DejaVuSans-Bold.ttf"),
            size=size,
        )
    except Exception:
        return ImageFont.load_default()


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255
    )
    return mask


def _panel(canvas, box, radius, fill, outline=None, width=1):
    """Semi-transparent rounded panel composited onto the canvas."""
    lay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(
        box, radius=radius, fill=fill, outline=outline, width=width
    )
    canvas.alpha_composite(lay)


def _icon(draw, kind, cx, cy, s, color):
    """Small line icons drawn with primitives (s = icon size in px)."""
    h = s / 2
    w = max(2, int(s / 10))
    if kind == "calendar":
        draw.rounded_rectangle(
            (cx - h, cy - h * 0.7, cx + h, cy + h), radius=3, outline=color, width=w
        )
        draw.line((cx - h, cy - h * 0.2, cx + h, cy - h * 0.2), fill=color, width=w)
        for dx in (-h * 0.5, h * 0.5):
            draw.line((cx + dx, cy - h, cx + dx, cy - h * 0.45), fill=color, width=w)
        for gx in (-0.5, 0, 0.5):
            for gy in (0.25, 0.65):
                draw.rectangle(
                    (
                        cx + gx * h - 1.5,
                        cy + gy * h - 1.5,
                        cx + gx * h + 1.5,
                        cy + gy * h + 1.5,
                    ),
                    fill=color,
                )
    elif kind == "people":
        for dx, r in ((-h * 0.45, h * 0.3), (h * 0.45, h * 0.3), (0, h * 0.36)):
            draw.ellipse(
                (cx + dx - r, cy - h * 0.55 - r, cx + dx + r, cy - h * 0.55 + r),
                outline=color,
                width=w,
            )
            draw.arc(
                (cx + dx - r * 1.7, cy - h * 0.05, cx + dx + r * 1.7, cy + h * 1.6),
                180,
                360,
                fill=color,
                width=w,
            )
    elif kind == "document":
        draw.polygon(
            [
                (cx - h * 0.7, cy - h),
                (cx + h * 0.3, cy - h),
                (cx + h * 0.7, cy - h * 0.6),
                (cx + h * 0.7, cy + h),
                (cx - h * 0.7, cy + h),
            ],
            outline=color,
            width=w,
        )
        for gy in (-0.35, 0.05):
            draw.line(
                (cx - h * 0.4, cy + gy * h, cx + h * 0.4, cy + gy * h),
                fill=color,
                width=w,
            )
        draw.ellipse(
            (cx + h * 0.15, cy + h * 0.2, cx + h * 0.95, cy + h * 1.0), fill=color
        )
        draw.line(
            (
                cx + h * 0.33,
                cy + h * 0.6,
                cx + h * 0.5,
                cy + h * 0.78,
                cx + h * 0.8,
                cy + h * 0.42,
            ),
            fill=(255, 255, 255),
            width=2,
        )
    elif kind == "coins":
        for i in range(3):
            y = cy + h * 0.55 - i * h * 0.45
            draw.ellipse(
                (cx - h * 0.8, y - h * 0.28, cx + h * 0.8, y + h * 0.28),
                fill=color,
                outline=(255, 255, 255),
                width=1,
            )
    elif kind == "shield":
        pts = [
            (cx, cy - h),
            (cx + h * 0.8, cy - h * 0.6),
            (cx + h * 0.7, cy + h * 0.3),
            (cx, cy + h),
            (cx - h * 0.7, cy + h * 0.3),
            (cx - h * 0.8, cy - h * 0.6),
        ]
        draw.polygon(pts, outline=color, width=w)
        draw.line(
            (
                cx - h * 0.35,
                cy,
                cx - h * 0.05,
                cy + h * 0.3,
                cx + h * 0.4,
                cy - h * 0.3,
            ),
            fill=color,
            width=w,
        )
    elif kind == "chart":
        for i, bh in enumerate((0.4, 0.7, 1.0)):
            x = cx - h * 0.8 + i * h * 0.6
            draw.rectangle((x, cy + h - bh * h * 1.4, x + h * 0.35, cy + h), fill=color)
        draw.line(
            (
                cx - h * 0.9,
                cy - h * 0.1,
                cx - h * 0.2,
                cy - h * 0.6,
                cx + h * 0.2,
                cy - h * 0.4,
                cx + h * 0.9,
                cy - h,
            ),
            fill=color,
            width=w,
        )
    elif kind == "check":
        draw.ellipse((cx - h, cy - h, cx + h, cy + h), fill=color)
        draw.line(
            (
                cx - h * 0.45,
                cy,
                cx - h * 0.1,
                cy + h * 0.38,
                cx + h * 0.5,
                cy - h * 0.35,
            ),
            fill=(255, 255, 255),
            width=max(2, w),
        )


def _slanted_text(canvas, xy_center, parts, font):
    """Bold slanted greeting (no script font ships with the server). parts = [(text, colour)]."""
    tmp = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [_text_size(tmp, t + " ", font)[0] for t, _ in parts[:-1]] + [
        _text_size(tmp, parts[-1][0], font)[0]
    ]
    tw, th = sum(widths), font.size + 16
    lay = Image.new("RGBA", (tw + 40, th + 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x = 20
    for (text, color), w in zip(parts, widths):
        d.text((x, 4), text, font=font, fill=color)
        x += w
    shear = 0.18
    lay = lay.transform(
        lay.size,
        Image.AFFINE,
        (1, shear, -shear * lay.size[1] / 2, 0, 1, 0),
        resample=Image.BICUBIC,
    )
    cx, cy = xy_center
    canvas.alpha_composite(lay, (int(cx - lay.size[0] / 2), int(cy - lay.size[1] / 2)))
    return tw


def _cover_crop_top(img, w, h):
    """Cover-fit like _cover_crop, but keep the upper part of tall photos (faces sit near the top)."""
    scale = max(w / img.size[0], h / img.size[1])
    nw, nh = max(1, round(img.size[0] * scale)), max(1, round(img.size[1] * scale))
    img = img.resize((nw, nh), RESAMPLE)
    left, top = (nw - w) // 2, int((nh - h) * 0.2)
    return img.crop((left, top, left + w, top + h))


def _photo_panel(canvas, photo):
    """Agent photo in a white rounded frame, with a small PadosiAgent logo badge below it."""
    box = (44, 40, 348, 452)  # 304 x 412, portrait
    w, h = box[2] - box[0], box[3] - box[1]
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0] + 2, box[1] + 8, box[2] + 2, box[3] + 10), radius=24, fill=(0, 0, 0, 110))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)))
    _panel(canvas, (box[0] - 6, box[1] - 6, box[2] + 6, box[3] + 6), 26, (255, 255, 255, 255))
    if photo.mode in ("RGBA", "LA", "P"):
        photo = photo.convert("RGBA")
        flat = Image.new("RGB", photo.size, (255, 255, 255))
        flat.paste(photo, mask=photo.split()[-1])
        photo = flat
    canvas.paste(_cover_crop_top(photo.convert("RGB"), w, h), box[:2], _rounded_mask((w, h), 20))
    logo = _load_rgba(os.path.join(settings.BASE_DIR, "static", "img", "logo.png"))
    if logo:
        lw = 190
        logo = logo.resize((lw, int(logo.size[1] * lw / logo.size[0])), RESAMPLE)
        pill = (196 - lw // 2 - 16, box[3] - 20, 196 + lw // 2 + 16, box[3] - 20 + logo.size[1] + 14)
        _panel(canvas, pill, (pill[3] - pill[1]) // 2, (255, 255, 255, 250), outline=(233, 185, 73, 255), width=2)
        canvas.alpha_composite(logo, (196 - lw // 2, pill[1] + 7))


def _load_rgba(path):
    try:
        return Image.open(path).convert("RGBA") if path else None
    except Exception:
        return None


def render_festive_card(agent, theme, profile=None, perf=None):
    from apps.admin_panel.services.agent_card_themes import (
        background_file_path,
        image_file_path,
    )

    profile, perf = _load_card_sources(agent, profile, perf)
    card = _card_data(agent, profile, perf)
    art = _load_rgba(background_file_path(theme))
    if art is None:  # no artwork uploaded: festive purple gradient
        art = Image.new("RGBA", (W, H), (76, 29, 149, 255))
        ImageDraw.Draw(art).ellipse((300, 0, 1100, 630), fill=(190, 84, 150, 255))
        art = art.filter(ImageFilter.GaussianBlur(120))
    art = _cover_crop(art.convert("RGB"), W, H).convert("RGBA")

    # Full-bleed: the artwork fills the whole 1200x630 image (WhatsApp shows all of it).
    canvas = art
    draw = ImageDraw.Draw(canvas)

    # Left: the agent's photo, or the site's default avatar (same as the Find Agents card)
    photo = _load_photo(agent, profile) or _load_rgba(os.path.join(settings.BASE_DIR, "static", "img", "avatar-icon.jpg"))
    if photo is not None:
        _photo_panel(canvas, photo)

    # Info panel (right)
    _panel(canvas, INFO, 24, (255, 251, 245, 238), outline=(255, 255, 255, 220), width=2)
    draw = ImageDraw.Draw(canvas)
    right = INFO[2] - 22
    badge_font = _font(True, 17)
    badges = []
    if card["show_licensed"]:
        badges.append(("Licensed", (243, 238, 255), (167, 139, 250), (91, 33, 182)))
    if card["show_trusted"]:
        badges.append(("Trusted", (236, 253, 245), (110, 231, 183), (4, 120, 87)))
    badge_ws = [_text_size(draw, b[0], badge_font)[0] + 54 for b in badges]
    name_room = right - X0 - sum(badge_ws) - 12 * len(badges) - (16 if badges else 0)
    name_font = _shrink_font(draw, card["name"], _font(True, 36), name_room, 22)
    name = _fit_text(draw, card["name"], name_font, name_room)
    name_color = _hex_rgb(theme.get("name_color"), NAVY) if theme.get("name_color") else NAVY
    draw.text((X0, 78), name, font=name_font, fill=name_color, anchor="lm")
    bx = X0 + _text_size(draw, name, name_font)[0] + 16
    for (label, fill, border, color), bw in zip(badges, badge_ws):
        draw.rounded_rectangle((bx, 61, bx + bw, 95), radius=17, fill=fill, outline=border, width=2)
        _icon(draw, "check", bx + 21, 78, 18, color)
        draw.text((bx + 37, 78), label, font=badge_font, fill=color, anchor="lm")
        bx += bw + 12
    sub_font = _font(True, 20)
    draw.text((X0, 121), _fit_text(draw, card["subtitle"], sub_font, right - X0), font=sub_font, fill=(91, 33, 182), anchor="lm")

    meta_y, mx = 162, X0
    if card["review_count"]:
        score = f"{card['rating']:.1f}"
        count = f"({card['review_count']} review{'s' if card['review_count'] != 1 else ''})"
        sw, cw_ = _text_size(draw, score, _font(True, 18))[0], _text_size(draw, count, _font(False, 17))[0]
        pill_w = 18 + 22 + 10 + sw + 7 + cw_ + 18
        draw.rounded_rectangle((mx, meta_y - 17, mx + pill_w, meta_y + 17), radius=17, fill=(255, 247, 230), outline=(246, 214, 160), width=2)
        _draw_star(draw, mx + 29, meta_y, 11, fill=(245, 158, 11))
        draw.text((mx + 50, meta_y), score, font=_font(True, 18), fill=NAVY, anchor="lm")
        draw.text((mx + 57 + sw, meta_y), count, font=_font(False, 17), fill=NAVY, anchor="lm")
        mx += pill_w + 26
    if card["location"]:
        _draw_pin(draw, mx + 7, meta_y, fill=NAVY)
        draw.text((mx + 24, meta_y), _fit_text(draw, card["location"], _font(False, 18), right - mx - 24), font=_font(False, 18), fill=NAVY, anchor="lm")

    stats = card["stats"][:4]
    top = STAT_ROW[0] if (card["review_count"] or card["location"]) else 146
    box_h = STAT_ROW[1] - STAT_ROW[0]
    if stats:
        gap = 16
        box_w = min(176, (right - X0 - gap * (len(stats) - 1)) // len(stats))
        for i, (val, lbl, _green) in enumerate(stats):
            fill, border, icon_color, icon = STAT_STYLE.get(lbl, ((248, 250, 252), (226, 232, 240), NAVY, "chart"))
            x = X0 + i * (box_w + gap)
            draw.rounded_rectangle((x, top, x + box_w, top + box_h), radius=14, fill=fill, outline=border, width=2)
            _icon(draw, icon, x + box_w / 2, top + 25, 26, icon_color)
            num_font = _shrink_font(draw, val, _font(True, 32), box_w - 16, 18)
            draw.text((x + box_w / 2, top + 63), val, font=num_font, fill=NAVY, anchor="mm")
            draw.text((x + box_w / 2, top + 95), lbl, font=_font(True, 15), fill=(51, 48, 105), anchor="mm")
        top += box_h

    pills_top, px = top + 16, X0
    pill_font = _font(True, 17)
    for item in card["segments"][:3]:
        fill, border, color = PILL_COLORS.get(item.get("class"), ((241, 245, 249), (203, 213, 225), (51, 65, 85)))
        if item.get("class") == "sme":
            fill, border, color = (255, 243, 224), (246, 197, 139), (154, 52, 18)
        pw = _text_size(draw, item["name"], pill_font)[0] + 56
        if px + pw > right:
            break
        draw.rounded_rectangle((px, pills_top, px + pw, pills_top + 34), radius=17, fill=fill, outline=border, width=2)
        _icon(draw, "shield", px + 21, pills_top + 17, 18, color)
        draw.text((px + 37, pills_top + 17), item["name"], font=pill_font, fill=color, anchor="lm")
        px += pw + 10
    content_bottom = pills_top + 34 if card["segments"] else pills_top

    # Greeting with a decoration (e.g. diya) on each side
    title = theme.get("greeting_title") or ""
    if title:
        gcx = (X0 + right) / 2 + 8
        words = title.split()
        accent = _hex_rgb(theme.get("greeting_color"), ORANGE) if theme.get("greeting_color") else ORANGE
        parts = [(" ".join(words[:-1]), NAVY), (words[-1], accent)] if len(words) > 1 else [(title, accent)]
        title_font = _font(True, 52)
        while title_font.size > 28 and _text_size(draw, title, title_font)[0] > 470:
            title_font = title_font.font_variant(size=title_font.size - 2)
        # centred in the space left under the details (higher on a sparse card)
        ty = max(content_bottom + 30, (content_bottom + INFO[3]) / 2 - 42)
        tw = _slanted_text(canvas, (gcx, ty), parts, title_font)
        draw = ImageDraw.Draw(canvas)
        for sign in (-1, 1):  # flourishes
            x1 = gcx + sign * (tw / 2 + 20)
            draw.line((x1, ty + 5, x1 + sign * 52, ty + 5), fill=accent, width=3)
            draw.ellipse((x1 + sign * 52 - 4, ty + 1, x1 + sign * 52 + 4, ty + 9), fill=accent)
        msg_font = _font(False, 18)
        lines = _wrap_lines(draw, theme.get("greeting_text") or "", msg_font, 480, 2)
        y = ty + 42
        for line in lines:
            draw.text((gcx, y), line, font=msg_font, fill=NAVY, anchor="mm")
            y += 25
        if lines:
            draw.line((gcx - 120, y + 2, gcx - 12, y + 2), fill=accent, width=2)
            draw.line((gcx + 12, y + 2, gcx + 120, y + 2), fill=accent, width=2)
            draw.polygon([(gcx, y - 5), (gcx + 7, y + 2), (gcx, y + 9), (gcx - 7, y + 2)], fill=accent)
        deco = _load_rgba(image_file_path(theme.get("decoration_image")))
        if deco:
            size = 132
            deco = deco.resize((size, int(deco.size[1] * size / deco.size[0])), RESAMPLE)
            dy = int(ty - deco.size[1] / 2 + 40)
            # outside the wider of title and message, so the diyas never touch the text
            half = max(tw / 2 + 74, max((_text_size(draw, ln, msg_font)[0] for ln in lines), default=0) / 2 + 16)
            canvas.alpha_composite(deco, (max(INFO[0] - 10, int(gcx - half - size)), dy))
            canvas.alpha_composite(deco.transpose(Image.FLIP_LEFT_RIGHT), (min(INFO[2] - size + 10, int(gcx + half)), dy))
            draw = ImageDraw.Draw(canvas)

    # Gold frame just inside the image edge
    draw.rounded_rectangle(CARD, radius=26, outline=GOLD, width=4)

    # Footer bar
    bar = (230, 536, 1164, 596)
    footer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(footer).rounded_rectangle(bar, radius=30, fill=(58, 22, 112, 245), outline=GOLD, width=2)
    canvas.alpha_composite(footer)
    draw = ImageDraw.Draw(canvas)
    mid = (bar[1] + bar[3]) // 2
    # WhatsApp: green app tile with a chat bubble; Call: blue circle
    draw.rounded_rectangle((262, mid - 19, 300, mid + 19), radius=10, fill=(37, 211, 102))
    draw.ellipse((269, mid - 12, 293, mid + 12), outline=(255, 255, 255), width=3)
    draw.polygon([(269, mid + 14), (272, mid + 6), (277, mid + 10)], fill=(255, 255, 255))
    draw.text((281, mid + 1), "☎", font=_symbol_font(12), fill=(255, 255, 255), anchor="mm")
    draw.ellipse((314, mid - 19, 352, mid + 19), fill=(59, 130, 246), outline=(255, 255, 255), width=2)
    draw.text((333, mid + 1), "☎", font=_symbol_font(19), fill=(255, 255, 255), anchor="mm")
    foot_font = _font(True, 22)
    draw.text((372, mid), "Direct WhatsApp & Calls · Zero middlemen", font=foot_font, fill=(255, 255, 255), anchor="lm")
    if card["show_verified"]:
        draw.line((838, bar[1] + 11, 838, bar[3] - 11), fill=(196, 181, 253), width=1)
        _icon(draw, "check", 882, mid, 30, (34, 197, 94))
        draw.text((906, mid), "PadosiAgent Verified", font=foot_font, fill=(255, 255, 255), anchor="lm")

    buf = io.BytesIO()
    from apps.agents.services.og_image import JPEG_QUALITY

    canvas.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


__all__ = ["render_festive_card"]
