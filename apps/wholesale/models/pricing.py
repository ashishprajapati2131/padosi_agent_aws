"""
Wholesale Volume Pricing Tiers.
"""
from django.db import models
from django.core.exceptions import ValidationError
from .product import WholesaleProduct

class WholesalePriceTier(models.Model):
    """
    Quantity-based price tiers (e.g. 10-49 units: Rs 500, 50-99 units: Rs 450, 100+: Rs 400).
    """
    
    product = models.ForeignKey(
        WholesaleProduct,
        on_delete=models.CASCADE,
        related_name='price_tiers'
    )
    min_quantity = models.PositiveIntegerField(help_text="Starting quantity for this price bracket")
    max_quantity = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Ending quantity (leave empty for unlimited/open-ended tier, e.g. '100+')"
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Price per unit in this tier"
    )

    class Meta:
        db_table = 'ws_price_tiers'
        verbose_name = 'Wholesale Price Tier'
        verbose_name_plural = 'Wholesale Price Tiers'
        ordering = ['min_quantity']

    def __str__(self):
        if self.max_quantity:
            return f"{self.min_quantity} - {self.max_quantity} units: ₹{self.unit_price}"
        return f"{self.min_quantity}+ units: ₹{self.unit_price}"

    def clean(self):
        if self.max_quantity is not None and self.min_quantity > self.max_quantity:
            raise ValidationError("Minimum quantity cannot be greater than maximum quantity.")
