import io
from PIL import Image
from fastapi import HTTPException, status

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
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp"}
    filename_lower = filename.lower()
    if not any(filename_lower.endswith(ext) for ext in allowed_exts):
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
