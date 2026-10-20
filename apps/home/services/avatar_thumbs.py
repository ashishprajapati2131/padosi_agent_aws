import logging
import os
from urllib.parse import urlparse

from PIL import Image, ImageOps
from django.conf import settings

logger = logging.getLogger(__name__)

THUMB_DIR = 'thumbs'


def small_avatar_url(url, size=96):
    """
    Return a URL for a small square WebP copy of a local /media/ image.

    Testimonial avatars are shown at ~40px but agent photos are 500px PNG/JPEG
    (up to ~600 KB each). The thumbnail is written once to
    MEDIA_ROOT/thumbs/<size>/ and reused; any non-local URL or failure falls
    back to the original URL.
    """
    if not url:
        return url
    path = urlparse(url).path
    media_url = settings.MEDIA_URL
    if not path.startswith(media_url) or f'/{THUMB_DIR}/' in path:
        return url

    rel_path = path[len(media_url):]
    media_root = os.path.realpath(settings.MEDIA_ROOT)
    src = os.path.realpath(os.path.join(media_root, rel_path))
    if not src.startswith(media_root + os.sep) or not os.path.isfile(src):
        return url

    thumb_rel = f"{THUMB_DIR}/{size}/{os.path.splitext(rel_path)[0]}.webp"
    thumb_abs = os.path.join(media_root, thumb_rel)
    try:
        if not os.path.exists(thumb_abs) or os.path.getmtime(thumb_abs) < os.path.getmtime(src):
            os.makedirs(os.path.dirname(thumb_abs), exist_ok=True)
            with Image.open(src) as img:
                img = ImageOps.exif_transpose(img).convert('RGB')
                img = ImageOps.fit(img, (size, size), Image.LANCZOS)
                img.save(thumb_abs, 'WEBP', quality=80, method=6)
    except Exception:
        logger.warning('Avatar thumbnail failed for %s', src, exc_info=True)
        return url
    return f"{media_url}{thumb_rel}"
