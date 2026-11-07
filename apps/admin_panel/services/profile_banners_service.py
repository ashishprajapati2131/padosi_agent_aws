"""Profile banner preset write flows used by apps/admin_panel/views/profile_banners.py."""

import re
import time

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.agents.models import ProfileBannerPreset, AgentProfile
from apps.home.models.site_setting import SiteSetting


def create_preset(title, category, display_order, file_bytes, safe_ext):
    """Save the validated image to storage and create an active preset."""
    timestamp = int(time.time())
    clean_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title.lower())[:30]
    file_path = f"banners/presets/{clean_title}_{timestamp}{safe_ext}"
    saved_path = default_storage.save(file_path, ContentFile(file_bytes))

    return ProfileBannerPreset.objects.create(
        title=title,
        category=category,
        image_path=saved_path,
        display_order=display_order,
        is_active=True,
    )


def toggle_preset(preset):
    preset.is_active = not preset.is_active
    preset.save(update_fields=["is_active", "updated_at"])


def delete_preset(preset):
    """Unlink agents, delete the preset, then best-effort delete its image file."""
    image_path = preset.image_path

    # Unlink any agents using this preset
    AgentProfile.objects.filter(banner_preset=preset).update(banner_preset=None)

    preset.delete()

    # Try deleting file if in presets folder and exists
    try:
        if image_path and default_storage.exists(image_path):
            default_storage.delete(image_path)
    except Exception:
        pass


def save_banner_settings(banner_enabled, allow_custom):
    SiteSetting.set_value("profile_banner_enabled", banner_enabled, group="agents")
    SiteSetting.set_value(
        "profile_banner_allow_custom_upload", allow_custom, group="agents"
    )
    SiteSetting.flush_cache()
