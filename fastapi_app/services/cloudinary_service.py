import logging
import cloudinary
import cloudinary.uploader
from fastapi_app.config import settings

logger = logging.getLogger(__name__)

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

# Warn immediately at startup if credentials are missing so it's obvious in logs
if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
    logger.warning(
        "⚠️  Cloudinary credentials are missing or incomplete. "
        "Set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env. "
        "All image uploads will fall back to local storage until this is fixed."
    )
else:
    logger.info(f"✓ Cloudinary configured: cloud_name={settings.CLOUDINARY_CLOUD_NAME}")


class CloudinaryService:
    @staticmethod
    def upload_image(file_bytes: bytes, folder: str, filename: str = None) -> str:
        """
        Uploads image bytes to Cloudinary and returns the secure URL.
        Raises an exception (which the caller catches to trigger fallback) on failure.
        """
        if not all([settings.CLOUDINARY_CLOUD_NAME, settings.CLOUDINARY_API_KEY, settings.CLOUDINARY_API_SECRET]):
            raise RuntimeError(
                "Cloudinary credentials not configured. "
                "Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET to .env"
            )

        options = {
            "folder": folder,
            "overwrite": True,
            "resource_type": "image"
        }
        if filename:
            options["public_id"] = filename

        logger.info(f"Uploading to Cloudinary: folder={folder}, filename={filename}")
        res = cloudinary.uploader.upload(file_bytes, **options)
        secure_url = res.get("secure_url")
        if not secure_url:
            raise RuntimeError(f"Cloudinary upload succeeded but returned no secure_url. Response: {res}")
        logger.info(f"Cloudinary upload successful: {secure_url}")
        return secure_url

    @staticmethod
    def delete_image(url_or_public_id: str) -> bool:
        """
        Deletes an image from Cloudinary using its secure URL or public ID.
        """
        if not url_or_public_id:
            return False

        public_id = url_or_public_id
        # Extract public_id from secure URL if needed
        # URL format: https://res.cloudinary.com/{cloud_name}/image/upload/v{version}/{folder}/{public_id_with_extension}
        if "res.cloudinary.com" in url_or_public_id:
            try:
                parts = url_or_public_id.split("/image/upload/")
                if len(parts) > 1:
                    # Skip version segment (e.g. v1625078400)
                    path_parts = parts[1].split("/")
                    if path_parts[0].startswith("v") and path_parts[0][1:].isdigit():
                        public_id_with_ext = "/".join(path_parts[1:])
                    else:
                        public_id_with_ext = "/".join(path_parts)
                    # Strip extension
                    public_id = public_id_with_ext.rsplit(".", 1)[0]
            except Exception:
                pass

        try:
            res = cloudinary.uploader.destroy(public_id)
            return res.get("result") == "ok"
        except Exception as e:
            logger.warning(f"Cloudinary delete failed for {public_id}: {e}")
            return False
