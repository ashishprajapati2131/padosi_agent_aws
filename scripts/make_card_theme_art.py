"""Draws the sample Diwali artwork shipped with the 'Diwali' agent card theme preset.

    python scripts/make_card_theme_art.py

Writes static/img/card_themes/diwali_bg.jpg (1200x630 share-card background) and
static/img/card_themes/diwali_diya.png (transparent diya, used as the decoration).
All shapes are drawn here, so the art has no third-party licence. Coordinates are
share-card pixels: the info card covers x 20-1180, y 85-545, so festive detail sits
around its edges (fireworks top-left, lanterns and marigolds top-right, skyline and
rangoli on the left, mandala bottom-right).
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1200, 630
OUT = os.path.join(os.path.dirname(__file__), "..", "static", "img", "card_themes")
random.seed(2026)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def background():
    """Purple edges with a bright cream-pink centre and a warm right side, like the reference."""
    img = Image.new("RGB", (W, H))
    px = img.load()
    deep, violet, cream, gold = (58, 20, 120), (128, 60, 180), (255, 244, 246), (255, 214, 150)
    for y in range(H):
        for x in range(W):
            t = (x / W) * 0.55 + (y / H) * 0.45
            c = lerp(deep, violet, min(1.0, t * 1.4))
            centre = max(0.0, 1 - math.hypot((x - 650) / 700, (y - 300) / 380))
            warm = max(0.0, 1 - math.hypot((x - 1060) / 420, (y - 360) / 320))
            c = lerp(c, gold, warm * 0.45)
            px[x, y] = lerp(c, cream, min(1.0, centre * 1.3))
    return img.convert("RGBA")


def bokeh(img):
    lay = layer()
    d = ImageDraw.Draw(lay)
    for _ in range(90):
        x, y, r = random.randint(0, W), random.randint(0, H), random.randint(3, 14)
        d.ellipse(
            (x - r, y - r, x + r, y + r), fill=(255, 214, 140, random.randint(25, 70))
        )
    return Image.alpha_composite(img, lay.filter(ImageFilter.GaussianBlur(3)))


def firework(img, cx, cy, radius, color, rays=28):
    glow, sharp = layer(), layer()
    g, s = ImageDraw.Draw(glow), ImageDraw.Draw(sharp)
    for i in range(rays):
        a = math.radians(i * 360 / rays + random.uniform(-3, 3))
        r = radius * random.uniform(0.75, 1.0)
        x2, y2 = cx + r * math.cos(a), cy + r * math.sin(a)
        g.line((cx, cy, x2, y2), fill=color + (150,), width=4)
        s.line(
            (cx + r * 0.35 * math.cos(a), cy + r * 0.35 * math.sin(a), x2, y2),
            fill=(255, 245, 210, 220),
            width=2,
        )
        s.ellipse((x2 - 3, y2 - 3, x2 + 3, y2 + 3), fill=color + (255,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(4)))
    return Image.alpha_composite(img, sharp)


def lanterns_and_marigolds(img):
    lay = layer()
    d = ImageDraw.Draw(lay)
    # marigold strings hanging from the top-right corner
    for i, x in enumerate(range(1030, 1172, 20)):
        length = 70 + (i % 4) * 28
        d.line((x, 0, x, length), fill=(120, 60, 20, 200), width=2)
        for y in range(8, length, 14):
            col = (255, 140, 0, 255) if (y // 14 + i) % 2 else (255, 196, 0, 255)
            d.ellipse((x - 7, y - 7, x + 7, y + 7), fill=col)
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(200, 80, 0, 255))
    glow = layer()
    gd = ImageDraw.Draw(glow)
    for cx, top, size in ((1075, 150, 30), (1120, 205, 36), (1158, 130, 26)):
        d.line((cx, 0, cx, top), fill=(212, 160, 60, 230), width=2)
        body = [
            (cx - size * 0.45, top + size * 0.35),
            (cx + size * 0.45, top + size * 0.35),
            (cx + size * 0.6, top + size * 1.1),
            (cx, top + size * 1.6),
            (cx - size * 0.6, top + size * 1.1),
        ]
        gd.ellipse(
            (cx - size * 1.4, top - size * 0.2, cx + size * 1.4, top + size * 2.2),
            fill=(255, 190, 80, 90),
        )
        d.rectangle(
            (cx - size * 0.35, top, cx + size * 0.35, top + size * 0.35),
            fill=(184, 134, 11, 255),
        )
        d.polygon(body, fill=(255, 176, 30, 255), outline=(150, 95, 10, 255))
        d.line(
            (cx, top + size * 0.35, cx, top + size * 1.6),
            fill=(255, 226, 140, 255),
            width=2,
        )
        d.line(
            (cx, top + size * 1.6, cx, top + size * 2.1),
            fill=(212, 160, 60, 255),
            width=2,
        )
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(10)))
    return Image.alpha_composite(img, lay)


def mandala(img, cx, cy, r, alpha):
    lay = layer()
    d = ImageDraw.Draw(lay)
    for ring, petals in ((1.0, 24), (0.78, 18), (0.56, 12), (0.34, 8)):
        rr = r * ring
        for i in range(petals):
            a = math.radians(i * 360 / petals)
            px, py = cx + rr * math.cos(a), cy + rr * math.sin(a)
            pr = r * 0.11 * ring + 4
            d.ellipse(
                (px - pr, py - pr, px + pr, py + pr),
                outline=(255, 214, 150, alpha),
                width=2,
            )
        d.ellipse(
            (cx - rr, cy - rr, cx + rr, cy + rr),
            outline=(255, 214, 150, alpha // 2),
            width=1,
        )
    return Image.alpha_composite(img, lay)


def rangoli(img, cx, cy, r):
    """Layered pointed-petal rangoli with a dotted border."""
    lay = layer()
    d = ImageDraw.Draw(lay)
    rings = (  # (radius share, petals, colour, petal width share)
        (1.0, 16, (236, 72, 153), 0.22), (0.82, 16, (250, 204, 21), 0.2), (0.64, 12, (34, 160, 220), 0.22),
        (0.46, 12, (249, 115, 22), 0.24), (0.3, 8, (124, 58, 237), 0.3),
    )
    for k, (share, petals, color, width) in enumerate(rings):
        rr = r * share
        for i in range(petals):
            a = math.radians(i * 360 / petals + (k % 2) * (180 / petals))
            tip = (cx + rr * math.cos(a), cy + rr * math.sin(a))
            side = rr * width
            left = (cx + side * math.cos(a + 1.2), cy + side * math.sin(a + 1.2))
            right = (cx + side * math.cos(a - 1.2), cy + side * math.sin(a - 1.2))
            d.polygon([left, tip, right, (cx, cy)], fill=color + (255,), outline=(255, 255, 255, 200))
    for i in range(32):
        a = math.radians(i * 360 / 32)
        x, y = cx + r * 1.08 * math.cos(a), cy + r * 1.08 * math.sin(a)
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, 230))
    d.ellipse((cx - r * 0.14, cy - r * 0.14, cx + r * 0.14, cy + r * 0.14), fill=(255, 255, 255, 255))
    d.ellipse((cx - r * 0.07, cy - r * 0.07, cx + r * 0.07, cy + r * 0.07), fill=(220, 38, 38, 255))
    return Image.alpha_composite(img, lay)


def skyline(img):
    lay = layer()
    d = ImageDraw.Draw(lay)
    # water and a green bank under the city (left panel, below the logo block)
    for y in range(420, 470):
        t = (y - 420) / 50
        d.line((20, y, 380, y), fill=lerp((140, 190, 235), (90, 140, 210), t) + (255,))
    d.ellipse((-150, 462, 330, 700), fill=(22, 163, 74, 255))
    d.ellipse((-110, 476, 290, 720), fill=(34, 197, 94, 255))
    random.seed(7)
    x = 30
    while x < 370:
        w = random.randint(16, 30)
        h = random.randint(40, 120)
        col = lerp((150, 178, 222), (98, 128, 190), random.random())
        d.rectangle((x, 420 - h, x + w, 420), fill=col + (255,))
        for wy in range(420 - h + 6, 414, 9):
            for wx in range(x + 4, x + w - 3, 7):
                if random.random() < 0.6:
                    d.rectangle((wx, wy, wx + 2, wy + 3), fill=(255, 221, 140, 230))
        x += w + random.randint(2, 6)
    reflection = lay.crop((20, 380, 380, 420)).transpose(Image.FLIP_TOP_BOTTOM)
    reflection.putalpha(reflection.getchannel("A").point(lambda a: a * 0.25))
    lay.alpha_composite(reflection, (20, 420))
    return Image.alpha_composite(img, lay)


def diya(size=180):
    """A lit clay lamp on a transparent background."""
    s = size
    lay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (s * 0.2, s * 0.02, s * 0.8, s * 0.62), fill=(255, 190, 60, 150)
    )
    lay = Image.alpha_composite(lay, glow.filter(ImageFilter.GaussianBlur(s * 0.08)))
    d = ImageDraw.Draw(lay)
    # bowl
    d.chord((s * 0.08, s * 0.38, s * 0.92, s * 0.98), 0, 180, fill=(176, 72, 22, 255))
    d.chord((s * 0.14, s * 0.46, s * 0.86, s * 0.9), 0, 180, fill=(210, 105, 30, 255))
    d.ellipse((s * 0.08, s * 0.6, s * 0.92, s * 0.76), fill=(140, 52, 16, 255))
    d.ellipse((s * 0.16, s * 0.62, s * 0.84, s * 0.72), fill=(250, 190, 60, 255))
    for i in range(7):  # painted dots on the rim
        x = s * (0.2 + i * 0.1)
        d.ellipse((x - 4, s * 0.8 - 4, x + 4, s * 0.8 + 4), fill=(255, 220, 120, 255))
    # flame
    d.polygon(
        [
            (s * 0.5, s * 0.12),
            (s * 0.6, s * 0.42),
            (s * 0.5, s * 0.64),
            (s * 0.4, s * 0.42),
        ],
        fill=(255, 170, 20, 255),
    )
    d.polygon(
        [
            (s * 0.5, s * 0.26),
            (s * 0.55, s * 0.44),
            (s * 0.5, s * 0.6),
            (s * 0.45, s * 0.44),
        ],
        fill=(255, 245, 190, 255),
    )
    for fx, fy, fr in ((0.1, 0.86, 0.1), (0.9, 0.86, 0.1), (0.2, 0.93, 0.08), (0.8, 0.93, 0.08)):
        x, y, rad = s * fx, s * fy, s * fr
        for ring, col in ((1.0, (234, 88, 12, 255)), (0.72, (249, 115, 22, 255)), (0.45, (251, 191, 36, 255))):
            for i in range(10):
                a = math.radians(i * 36)
                px_, py_ = x + rad * 0.45 * ring * math.cos(a), y + rad * 0.45 * ring * math.sin(a)
                pr = rad * 0.42 * ring
                d.ellipse((px_ - pr, py_ - pr, px_ + pr, py_ + pr), fill=col)
    return lay


def main():
    os.makedirs(OUT, exist_ok=True)
    img = background()
    img = bokeh(img)
    for cx, cy, r, col in (
        (95, 120, 70, (255, 120, 180)),
        (240, 70, 85, (255, 196, 60)),
        (560, 30, 60, (255, 160, 60)),
        (905, 60, 55, (170, 120, 255)),
    ):
        img = firework(img, cx, cy, r, col)
    img = mandala(img, 1120, 520, 170, 70)
    img = lanterns_and_marigolds(img)
    img = skyline(img)
    img = rangoli(img, 98, 500, 74)
    img.convert("RGB").save(
        os.path.join(OUT, "diwali_bg.jpg"), "JPEG", quality=88, optimize=True
    )
    diya().save(os.path.join(OUT, "diwali_diya.png"), optimize=True)
    print("written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
