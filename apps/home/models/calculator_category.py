from django.db import models

from apps.home.models.calculator import flush_calculator_cache


class CalculatorCategory(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=64, unique=True)
    icon_class = models.CharField(max_length=80, default='fa-solid fa-folder')
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    meta_title = models.CharField(max_length=255, blank=True, default='')
    meta_description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'calculator_categories'
        ordering = ['sort_order', 'name']
        verbose_name_plural = 'calculator categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        flush_calculator_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        flush_calculator_cache()
