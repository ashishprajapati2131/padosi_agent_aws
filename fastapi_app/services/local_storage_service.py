import os
import uuid
from datetime import datetime
from app.config import settings

class LocalStorageService:
    @staticmethod
    def save_file(file_bytes: bytes, subfolder: str, filename: str, base_url: str = None) -> str:
        """
        Saves the file to local storage and returns its public URL.
        Layout: {LOCAL_STORAGE_PATH}/uploads/{subfolder}/{year}/{month}/{unique_filename}

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

        # Resolve base URL — prefer the caller-supplied value (live domain)
        effective_base_url = (base_url or settings.APP_URL).rstrip("/")

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

        # Return public URL path using the effective base URL
        relative_path = f"uploads/{subfolder}/{year_str}/{month_str}/{unique_name}"
        public_url = f"{effective_base_url}/static/{relative_path}"
        return public_url

    @staticmethod
    def delete_file(public_url: str) -> bool:
        """
        Deletes a local file from disk.
        """
        if not public_url:
            return False

        if "/static/uploads/" in public_url:
            try:
                parts = public_url.split("/static/")
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
