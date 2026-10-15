"""
Product Category and Subcategory Models for Wholesale Catalog.
"""
from django.db import models
from django.utils.text import slugify

class ProductCategory(models.Model):
    """Hierarchical category tree for wholesale products."""
    
    name = models.CharField(max_length=150, db_index=True)
    slug = models.SlugField(max_length=170, unique=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    icon_class = models.CharField(max_length=100, default='fa-solid fa-box', help_text="FontAwesome icon class")
    image = models.ImageField(upload_to='wholesale/categories/', blank=True, null=True)
    
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )
    
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'ws_categories'
        verbose_name = 'Product Category'
        verbose_name_plural = 'Product Categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while ProductCategory.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_subcategory(self):
        return self.parent is not None
