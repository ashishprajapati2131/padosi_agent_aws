"""
Wholesale Pricing Tier Service.
Handles tier validation, quantity-based price lookups, and savings calculation.
"""
from decimal import Decimal
from typing import List, Dict, Any
from django.core.exceptions import ValidationError
from apps.wholesale.models.pricing import WholesalePriceTier
from apps.wholesale.models.product import WholesaleProduct

class PricingService:
    """Business logic for tiered wholesale pricing calculations and validation."""

    @staticmethod
    def validate_tiers(product: WholesaleProduct, tiers_data: List[Dict[str, Any]]) -> List[str]:
        """
        Validates a list of tier dicts: [{'min_qty': 10, 'max_qty': 49, 'price': 500}, ...]
        Returns a list of error strings (empty if valid).
        """
        errors = []
        if not tiers_data:
            return errors

        # Sort tiers by min_quantity
        try:
            sorted_tiers = sorted(tiers_data, key=lambda x: int(x.get('min_qty', 0)))
        except (ValueError, TypeError):
            return ["Invalid numeric values in quantity tiers."]

        last_max = None
        last_price = None

        for idx, tier in enumerate(sorted_tiers):
            try:
                min_q = int(tier.get('min_qty', 0))
                max_q = int(tier['max_qty']) if tier.get('max_qty') not in (None, '', 'null') else None
                price = Decimal(str(tier.get('price', 0)))
            except Exception:
                errors.append(f"Tier #{idx + 1} has invalid numbers.")
                continue

            if min_q < 1:
                errors.append(f"Tier #{idx + 1}: Minimum quantity must be at least 1.")

            if max_q is not None:
                if min_q > max_q:
                    errors.append(f"Tier #{idx + 1}: Min quantity ({min_q}) cannot exceed Max quantity ({max_q}).")

            if last_max is not None:
                if min_q <= last_max:
                    errors.append(f"Tier #{idx + 1}: Overlaps with previous tier (starts at {min_q}, previous ended at {last_max}).")
                elif min_q != last_max + 1:
                    errors.append(f"Tier #{idx + 1}: There is a gap between {last_max} and {min_q}.")

            if last_price is not None:
                if price > last_price:
                    errors.append(f"Tier #{idx + 1}: Unit price (₹{price}) should be less than or equal to previous tier (₹{last_price}).")

            if max_q is None and idx != len(sorted_tiers) - 1:
                errors.append(f"Tier #{idx + 1}: Open-ended tier (no maximum) must be the last tier.")

            last_max = max_q
            last_price = price

        return errors

    @staticmethod
    def save_tiers_for_product(product: WholesaleProduct, tiers_data: List[Dict[str, Any]]):
        """Atomically replaces product price tiers after validation."""
        errors = PricingService.validate_tiers(product, tiers_data)
        if errors:
            raise ValidationError(errors)

        # Remove existing and recreate
        product.price_tiers.all().delete()
        for item in tiers_data:
            min_q = int(item['min_qty'])
            max_q = int(item['max_qty']) if item.get('max_qty') not in (None, '', 'null') else None
            price = Decimal(str(item['price']))
            WholesalePriceTier.objects.create(
                product=product,
                min_quantity=min_q,
                max_quantity=max_q,
                unit_price=price
            )

    @staticmethod
    def calculate_order_summary(product: WholesaleProduct, quantity: int) -> Dict[str, Any]:
        """
        Returns full cost breakdown for a given quantity:
        - unit_price
        - total_base
        - tax_amount
        - total_with_tax
        - savings_vs_base
        - active_tier_id
        """
        qty = max(quantity, product.moq)
        unit_price = product.get_price_for_quantity(qty)
        total_base = unit_price * Decimal(qty)
        
        # Calculate GST / Tax
        if product.tax_included:
            tax_rate = product.tax_rate_percent / Decimal(100)
            net_base = total_base / (Decimal(1) + tax_rate)
            tax_amount = total_base - net_base
            total_final = total_base
        else:
            tax_amount = (total_base * product.tax_rate_percent) / Decimal(100)
            total_final = total_base + tax_amount

        # Calculate savings compared to standard base price
        standard_total = product.base_price * Decimal(qty)
        savings = max(Decimal(0), standard_total - total_base)

        return {
            'quantity': qty,
            'unit_price': round(unit_price, 2),
            'total_base': round(total_base, 2),
            'tax_percent': product.tax_rate_percent,
            'tax_amount': round(tax_amount, 2),
            'total_with_tax': round(total_final, 2),
            'savings_vs_base': round(savings, 2),
            'currency': product.currency,
        }
