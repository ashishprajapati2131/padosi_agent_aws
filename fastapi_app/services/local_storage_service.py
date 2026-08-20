import os
import uuid
from datetime import datetime
from fastapi_app.config import settings

class LocalStorageService:
    @staticmethod
    def save_django_path_file(file_bytes: bytes, relative_path: str) -> str:
        """
        Saves the file to local storage exactly at the given relative path.
        Used to mirror Django's storage paths (e.g. app/public/insurance/...)
        """
        full_local_path = os.path.join(settings.LOCAL_STORAGE_PATH, relative_path)
        os.makedirs(os.path.dirname(full_local_path), exist_ok=True)
        
        with open(full_local_path, "wb") as f:
            f.write(file_bytes)
            
        return relative_path

    @staticmethod
    def save_file(file_bytes: bytes, subfolder: str, filename: str, base_url: str = None) -> str:
        """
        Args:
            file_bytes: Raw bytes of the file to save.
            subfolder:  Sub-directory name (e.g. "profile", "achievement").
            filename:   Original filename (used for extension detection).
            base_url:   Base URL to prefix the public path with.
                        Pass str(request.base_url).rstrip('/') from the route handler
                        so the URL reflects the live domain (ngrok / production).
                        Defaults to settings.APP_URL when not provided.
        """
        now = datetime.now()
        year_str = now.strftime("%Y")
        month_str = now.strftime("%m")

        # Base URL is no longer prepended to ensure proxy-agnostic relative paths.

        # Build upload directory path
        upload_dir = os.path.join(
            settings.LOCAL_STORAGE_PATH,
            "uploads",
            subfolder,
            year_str,
            month_str
        )

        # Ensure directories exist
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename to prevent collision and sanitize extension
        ext = os.path.splitext(filename)[1]
        if not ext:
            ext = ".png"
        unique_name = f"{uuid.uuid4().hex}_{int(now.timestamp())}{ext}"
        file_path = os.path.join(upload_dir, unique_name)

        # Write file content
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        # Return relative public URL path
        relative_path = f"uploads/{subfolder}/{year_str}/{month_str}/{unique_name}"
        public_url = f"/media/{relative_path}"
        return public_url

    @staticmethod
    def delete_file(public_url: str) -> bool:
        """
        Deletes a local file from disk.
        """
        if not public_url:
            return False

        if "/media/uploads/" in public_url:
            try:
                parts = public_url.split("/media/")
                if len(parts) > 1:
                    relative_path = parts[1]
                    # Secure check to prevent directory traversal
                    normalized_path = os.path.normpath(relative_path)
                    if normalized_path.startswith("..") or os.path.isabs(normalized_path):
                        return False

                    full_local_path = os.path.join(settings.LOCAL_STORAGE_PATH, normalized_path)
                    if os.path.exists(full_local_path):
                        os.remove(full_local_path)
                        return True
            except Exception:
                pass
        return False
