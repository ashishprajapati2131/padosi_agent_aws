import io
import os
from PIL import Image

# Extra extensions hidden in names such as report.js.jpg or page.html.png.
DANGEROUS_EXTENSIONS = frozenset({
    'js', 'jsx', 'mjs', 'cjs', 'ts', 'tsx', 'php', 'phtml', 'php3', 'php4', 'php5', 'phar',
    'asp', 'aspx', 'jsp', 'cgi', 'pl', 'py', 'rb', 'sh', 'bash', 'bat', 'cmd', 'ps1',
    'exe', 'dll', 'com', 'scr', 'msi', 'vbs', 'wsf', 'html', 'htm', 'svg', 'xml', 'xhtml',
    'htaccess', 'jar', 'war', 'swf', 'shtml',
})

EXTENSION_KIND = {
    '.jpg': 'jpeg',
    '.jpeg': 'jpeg',
    '.png': 'png',
    '.gif': 'gif',
    '.webp': 'webp',
    '.pdf': 'pdf',
}

DISGUISED_NAME_MESSAGE = (
    'This file name is not allowed. Use a single extension such as certificate.pdf. '
    'Renamed files like name.js.jpg cannot be uploaded.'
)
CONTENT_MISMATCH_MESSAGE = (
    'The file content does not match its extension. '
    'A renamed code or document file cannot be uploaded.'
)


def file_basename(filename):
    name = os.path.basename((filename or '').replace('\\', '/'))
    if '\x00' in name:
        return ''
    return name


def has_dangerous_extra_extension(filename):
    """True when a name hides a code or executable extension, e.g. evil.js.jpg."""
    parts = file_basename(filename).lower().split('.')
    if len(parts) <= 2:
        return False
    return any(part in DANGEROUS_EXTENSIONS for part in parts[1:-1])


def detect_binary_kind(content):
    """Return pdf, png, jpeg, webp, gif, or None from the file signature."""
    if not content:
        return None
    if content.startswith(b'%PDF-'):
        return 'pdf'
    if content[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if content[:2] == b'\xff\xd8':
        return 'jpeg'
    if (
        len(content) >= 12
        and content[:4] == b'RIFF'
        and content[8:12] == b'WEBP'
    ):
        return 'webp'
    if content[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    return None


def _verify_image(content):
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
        return True
    except Exception:
        return False


def validate_license_document(file_content, filename):
    """Validate an IRDAI or AMFI certificate.

    Returns (True, None, extension) or (False, error_message, None).
    Only a real PDF, JPG, JPEG, or PNG is accepted, and the bytes must match
    the extension. Names such as script.js.jpg are refused.
    """
    if not file_content:
        return False, 'The file is empty.', None
    if len(file_content) > 5 * 1024 * 1024:
        return False, 'File size must be under 5MB.', None

    base = file_basename(filename)
    if not base:
        return False, 'Please choose a valid file name.', None
    if has_dangerous_extra_extension(base):
        return False, DISGUISED_NAME_MESSAGE, None

    ext = os.path.splitext(base.lower())[1]
    allowed = {'.pdf', '.jpg', '.jpeg', '.png'}
    if ext not in allowed:
        return False, 'Only PDF, JPG, JPEG, and PNG files are allowed.', None

    kind = detect_binary_kind(file_content)
    if kind != EXTENSION_KIND[ext]:
        return False, CONTENT_MISMATCH_MESSAGE, None
    if kind != 'pdf' and not _verify_image(file_content):
        return False, 'Invalid or corrupted image file.', None
    return True, None, ext


def validate_magic_bytes(file_content, filename):
    """
    Validates a document file (PDF or Image) for format, extension, and integrity
    using magic bytes (file signature) checking.
    Supports: PDF, JPEG, JPG, PNG, WEBP.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    if has_dangerous_extra_extension(filename):
        return False, DISGUISED_NAME_MESSAGE

    base = file_basename(filename)
    ext = os.path.splitext(base.lower())[1]
    allowed_exts = {'.jpg', '.jpeg', '.png', '.pdf', '.webp'}
    if ext not in allowed_exts:
        return False, 'Invalid file extension. Only PDF, JPG, PNG, and WEBP are allowed.'

    kind = detect_binary_kind(file_content or b'')
    if kind != EXTENSION_KIND[ext]:
        if ext == '.pdf':
            return False, 'File signature mismatch. The file is not a valid PDF.'
        return False, CONTENT_MISMATCH_MESSAGE

    if kind == 'pdf':
        return True, None
    if not _verify_image(file_content):
        return False, 'Invalid or corrupted image file.'
    return True, None
