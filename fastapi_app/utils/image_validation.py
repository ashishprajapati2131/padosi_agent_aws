import io
import os
from PIL import Image
from fastapi import HTTPException, status

_DANGEROUS_EXTENSIONS = {
    'js', 'jsx', 'mjs', 'cjs', 'ts', 'tsx', 'php', 'phtml', 'php3', 'php4', 'php5', 'phar',
    'asp', 'aspx', 'jsp', 'cgi', 'pl', 'py', 'rb', 'sh', 'bash', 'bat', 'cmd', 'ps1',
    'exe', 'dll', 'com', 'scr', 'msi', 'vbs', 'wsf', 'html', 'htm', 'svg', 'xml', 'xhtml',
    'htaccess', 'jar', 'war', 'swf', 'shtml',
}
_DISGUISED_NAME = (
    'This file name is not allowed. Use a single extension such as certificate.pdf. '
    'Renamed files like name.js.jpg cannot be uploaded.'
)


def _basename(filename):
    name = os.path.basename((filename or '').replace('\\', '/'))
    if '\x00' in name:
        return ''
    return name


def _reject_disguised_name(filename):
    parts = _basename(filename).lower().split('.')
    if len(parts) > 2 and any(part in _DANGEROUS_EXTENSIONS for part in parts[1:-1]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DISGUISED_NAME,
        )

def validate_image_file(file_content: bytes, filename: str, content_type: str) -> bytes:
    """
    Validates the uploaded image file for size, format, extension, and integrity.
    Verifies actual file content using magic bytes and decodes/sanitizes the image.
    Returns the sanitized image bytes.
    Raises HTTPException (422) if validation fails.

    Supported formats: JPEG, JPG, PNG, WEBP
    """
    # 1. Size Check (20 MB)
    max_size = 20 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File size exceeds the maximum limit of 20 MB."
        )

    # 2. Extension Check
    _reject_disguised_name(filename)
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    filename_lower = _basename(filename).lower()
    ext = os.path.splitext(filename_lower)[1]
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid file extension. Only .jpg, .jpeg, .png, and .webp are allowed."
        )

    # 3. MIME Type Check
    allowed_mimes = {"image/jpeg", "image/jpg", "image/png", "image/pjpeg", "image/webp"}
    if content_type.lower() not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid image MIME type. Only image/jpeg, image/jpg, image/png, and image/webp are allowed."
        )

    # 4. Magic Bytes Check (validate actual file signature)
    # PNG magic bytes:  \x89PNG\r\n\x1a\n  (first 8 bytes)
    # JPEG magic bytes: \xff\xd8            (first 2 bytes — SOI marker)
    # WEBP magic bytes: RIFF....WEBP        (bytes 0-3 = "RIFF", bytes 8-11 = "WEBP")
    is_png  = file_content[:8] == b'\x89PNG\r\n\x1a\n'
    is_jpeg = file_content[:2] == b'\xff\xd8'
    is_webp = (
        len(file_content) >= 12 and
        file_content[:4] == b'RIFF' and
        file_content[8:12] == b'WEBP'
    )

    if not (is_png or is_jpeg or is_webp):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File signature (magic bytes) mismatch. The file is not a valid PNG, JPEG, or WEBP image."
        )
    expected = 'png' if ext == '.png' else 'webp' if ext == '.webp' else 'jpeg'
    detected = 'png' if is_png else 'webp' if is_webp else 'jpeg'
    if detected != expected:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The file content does not match its extension. A renamed code or document file cannot be uploaded."
        )

    # 5. Integrity Check & Sanitization (using Pillow)
    try:
        # Load and verify the file structure
        img = Image.open(io.BytesIO(file_content))
        img.verify()

        # Re-open, load, and re-save image to sanitize metadata and embedded payloads
        img = Image.open(io.BytesIO(file_content))
        img.load()  # Decodes pixels

        out_buf = io.BytesIO()
        if is_webp:
            img_format = "WEBP"
        elif is_png:
            img_format = "PNG"
        else:
            img_format = "JPEG"
        img.save(out_buf, format=img_format)
        return out_buf.getvalue()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid or corrupted image file."
        )


def validate_document_file(file_content: bytes, filename: str, content_type: str) -> bytes:
    """
    Validates a document file (PDF or Image) for size, format, extension, and integrity.
    Supports: PDF, JPEG, JPG, PNG.
    """
    # 1. Size Check (5 MB for documents)
    max_size = 5 * 1024 * 1024
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File size exceeds the maximum limit of 5 MB."
        )

    # 2. Extension Check
    _reject_disguised_name(filename)
    allowed_exts = {".jpg", ".jpeg", ".png", ".pdf"}
    filename_lower = _basename(filename).lower()
    ext = os.path.splitext(filename_lower)[1]
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid file extension. Only .pdf, .jpg, .jpeg, and .png are allowed."
        )

    # 3. MIME Type Check
    allowed_mimes = {"application/pdf", "image/jpeg", "image/jpg", "image/png"}
    if content_type.lower() not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid MIME type. Only application/pdf, image/jpeg, and image/png are allowed."
        )

    # 4. Handle PDF validation
    if ext == ".pdf":
        # Magic bytes for PDF: %PDF-
        if not file_content.startswith(b'%PDF-'):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="File signature (magic bytes) mismatch. The file is not a valid PDF."
            )
        return file_content

    # 5. Handle Image validation (delegate to validate_image_file, but avoid WEBP if not needed)
    try:
        return validate_image_file(file_content, filename, content_type)
    except HTTPException as e:
        raise e

