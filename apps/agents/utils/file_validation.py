import io
import os
from PIL import Image

def validate_magic_bytes(file_content, filename):
    """
    Validates a document file (PDF or Image) for format, extension, and integrity
    using magic bytes (file signature) checking.
    Supports: PDF, JPEG, JPG, PNG, WEBP.
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """
    filename_lower = filename.lower()
    ext = os.path.splitext(filename_lower)[1]
    
    # 1. Extension Check
    allowed_exts = {".jpg", ".jpeg", ".png", ".pdf", ".webp"}
    if ext not in allowed_exts:
        return False, "Invalid file extension. Only PDF, JPG, PNG, and WEBP are allowed."

    # 2. PDF Magic Bytes Check
    if ext == ".pdf":
        if not file_content.startswith(b'%PDF-'):
            return False, "File signature mismatch. The file is not a valid PDF."
        return True, None

    # 3. Image Magic Bytes Check
    is_png  = file_content[:8] == b'\x89PNG\r\n\x1a\n'
    is_jpeg = file_content[:2] == b'\xff\xd8'
    is_webp = (
        len(file_content) >= 12 and
        file_content[:4] == b'RIFF' and
        file_content[8:12] == b'WEBP'
    )

    if not (is_png or is_jpeg or is_webp):
        return False, "File signature mismatch. The file is not a valid PNG, JPEG, or WEBP image."

    # 4. Integrity Check (using Pillow)
    try:
        img = Image.open(io.BytesIO(file_content))
        img.verify()
        return True, None
    except Exception:
        return False, "Invalid or corrupted image file."
