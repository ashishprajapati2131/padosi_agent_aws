"""
Cross-Sell and Related Product Relationships.
"""
from django.db import models
from .product import WholesaleProduct

class ProductRelationship(models.Model):
    """Product associations for cross-selling and related discovery."""
    
    RELATIONSHIP_CHOICES = [
        ('RELATED', 'Related / Similar Product'),
        ('COMPLEMENTARY', 'Complementary / Frequently Paired'),
    ]
    
    source_product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='relationships_from'
    )
    target_product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='relationships_to'
    )
    relationship_type = models.CharField(
        max_length=30,
        choices=RELATIONSHIP_CHOICES,
        default='RELATED'
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'ws_product_relationships'
        verbose_name = 'Product Relationship'
        verbose_name_plural = 'Product Relationships'
        unique_together = ('source_product', 'target_product', 'relationship_type')
        ordering = ['display_order', 'id']

    def __str__(self):
        return f"{self.source_product.title} → {self.get_relationship_type_display()}: {self.target_product.title}"
