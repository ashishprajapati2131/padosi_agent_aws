from django.core.cache import cache
from django.db import models

NAV_CACHE_KEY = 'calculators_nav_active'


def flush_calculator_cache():
    cache.delete(NAV_CACHE_KEY)


class Calculator(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=255)
    short_description = models.TextField(blank=True, default='')
    category = models.ForeignKey(
        'home.CalculatorCategory',
        on_delete=models.PROTECT,
        related_name='calculators',
    )
    icon_class = models.CharField(max_length=80, default='fa-solid fa-calculator')
    is_active = models.BooleanField(default=False)
    engine_ready = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    meta_title = models.CharField(max_length=255, blank=True, default='')
    meta_description = models.TextField(blank=True, default='')
    disclaimer = models.TextField(blank=True, default='')
    cta_text = models.CharField(max_length=120, default='Find a PadosiAgent')
    cta_url = models.CharField(max_length=255, default='/find-agents/?openFilter=1')
    default_inputs = models.JSONField(blank=True, default=dict)
    faq_json = models.JSONField(blank=True, default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'calculators'
        ordering = ['sort_order', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        flush_calculator_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        flush_calculator_cache()

    @property
    def is_public(self):
        return bool(self.is_active and self.engine_ready)

    @property
    def category_slug(self):
        return self.category.slug if self.category_id else ''
