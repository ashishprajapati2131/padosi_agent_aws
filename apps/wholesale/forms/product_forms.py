"""
Product Wizard and Management Forms.
"""
from django import forms
from apps.wholesale.models.product import WholesaleProduct, ProductImage, ProductVariant
from apps.wholesale.models.category import ProductCategory

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class ProductWizardForm(forms.ModelForm):
    """Unified multi-step product wizard form handling validation across all steps."""
    
    primary_image = forms.ImageField(required=False, widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}))
    additional_images = forms.FileField(required=False, widget=MultipleFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}))
    price_tiers_json = forms.CharField(required=False, widget=forms.HiddenInput())
    variants_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = WholesaleProduct
        fields = [
            # Basic Information
            'title', 'category', 'sku', 'brand', 'condition', 'country_of_origin', 'tags',
            'short_description', 'description',
            # Pricing
            'base_price', 'suggested_retail_price', 'currency', 'tax_included', 'tax_rate_percent',
            'moq', 'max_order_quantity', 'unit_of_measure', 'pack_size', 'is_quote_only',
            # Inventory
            'stock_quantity', 'low_stock_threshold', 'lead_time_days', 'is_made_to_order',
            # Shipping
            'dispatch_location', 'shipping_regions', 'shipping_charge_policy', 'local_pickup_available',
            # Terms
            'return_policy', 'warranty_info', 'customization_available', 'sample_available',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'e.g. Policy Presentation Leatherette Folders'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. FOLD-LEATH-01'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Brand / Manufacturer name'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
            'country_of_origin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'India'}),
            'tags': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'folder, policy kit, stationery, agent supplies'}),
            'short_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Crisp 1-2 sentence overview for catalog cards'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Detailed specifications, grade, testing, packaging'}),

            # Pricing
            'base_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'suggested_retail_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'MSRP'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
            'tax_included': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tax_rate_percent': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'moq': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'max_order_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'Optional'}),
            'unit_of_measure': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Piece, Box, Kg, Carton'}),
            'pack_size': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 50 pieces in 1 master box'}),
            'is_quote_only': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # Inventory
            'stock_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'is_made_to_order': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # Shipping
            'dispatch_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City, State, Pincode'}),
            'shipping_regions': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Pan India / Gujarat / Ex-Factory'}),
            'shipping_charge_policy': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Paid by buyer via V-Trans / TCI'}),
            'local_pickup_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # Terms
            'return_policy': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Replacement for transit damage or manufacturing defects'}),
            'warranty_info': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12 Months standard warranty'}),
            'customization_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sample_available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_base_price(self):
        price = self.cleaned_data.get('base_price')
        if price is not None and price <= 0:
            raise forms.ValidationError("Base wholesale price must be greater than zero.")
        return price

    def clean_moq(self):
        moq = self.cleaned_data.get('moq')
        if moq is not None and moq < 1:
            raise forms.ValidationError("Minimum Order Quantity must be at least 1.")
        return moq
