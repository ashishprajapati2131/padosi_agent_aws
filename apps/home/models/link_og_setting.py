import os
from django.db import models
from django.core.cache import cache


class LinkOgSetting(models.Model):
    """
    Allows custom Open Graph (OG) image, title, and description for ANY URL/path.
    Admin can simply provide a path and upload an image — zero code changes needed.
    """
    path = models.CharField(
        max_length=240,
        unique=True,
        help_text="URL path, e.g. '/' or '/agent/registration/' or '/events/paldi/'"
    )
    image = models.CharField(
        max_length=500,
        help_text="Absolute URL or /media/ path to the OG image"
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Custom OG Title (optional)"
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text="Custom OG Description (optional)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable or disable this OG preview rule"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    CACHE_KEY = 'link_og_settings_all'

    class Meta:
        db_table = 'link_og_settings'
        ordering = ['path']
        verbose_name = 'Link OG Setting'
        verbose_name_plural = 'Link OG Settings'

    def __str__(self):
        return f"{self.path} -> {self.image}"

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize URL path for consistent lookups."""
        if not path:
            return '/'
        p = str(path).strip()
        # Remove query params or anchors if accidentally included
        if '?' in p:
            p = p.split('?')[0]
        if '#' in p:
            p = p.split('#')[0]
        if not p.startswith('/'):
            p = '/' + p
        return p

    @classmethod
    def get_all_active_map(cls) -> dict:
        """Returns cached dict mapping normalized paths to their metadata."""
        data = cache.get(cls.CACHE_KEY)
        if data is None:
            rules = cls.objects.filter(is_active=True)
            data = {}
            for r in rules:
                clean_path = cls.normalize_path(r.path)
                data[clean_path] = {
                    'image': r.image,
                    'title': r.title,
                    'description': r.description,
                }
                # Also index with/without trailing slash for forgiving matches
                if clean_path.endswith('/') and len(clean_path) > 1:
                    data[clean_path.rstrip('/')] = data[clean_path]
                elif not clean_path.endswith('/'):
                    data[clean_path + '/'] = data[clean_path]
            cache.set(cls.CACHE_KEY, data, timeout=None)
        return data or {}

    @classmethod
    def get_for_path(cls, path: str):
        """Finds custom OG metadata for a specific request path."""
        active_map = cls.get_all_active_map()
        clean = cls.normalize_path(path)
        return active_map.get(clean)

    @classmethod
    def flush_cache(cls):
        cache.delete(cls.CACHE_KEY)


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=LinkOgSetting)
@receiver(post_delete, sender=LinkOgSetting)
def clear_link_og_cache(sender, instance, **kwargs):
    LinkOgSetting.flush_cache()
