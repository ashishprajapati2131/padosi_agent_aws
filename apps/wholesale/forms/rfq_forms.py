"""
Buyer RFQ (Request for Quotation) Form.
"""
from django import forms
from apps.wholesale.models.inquiry import BuyerInquiry

class BuyerInquiryForm(forms.ModelForm):
    """RFQ modal form submitted by prospective buyers."""
    
    class Meta:
        model = BuyerInquiry
        fields = [
            'buyer_name', 'buyer_email', 'buyer_phone', 'company_name',
            'delivery_city', 'delivery_pincode', 'requested_quantity',
            'target_price_per_unit', 'expected_purchase_timeline', 'message'
        ]
        widgets = {
            'buyer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Full Name'}),
            'buyer_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@company.com'}),
            'buyer_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10-digit mobile number'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Agency / Firm / Store Name'}),
            'delivery_city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Delivery City'}),
            'delivery_pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Pincode'}),
            'requested_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'target_price_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Expected ₹ / unit'}),
            'expected_purchase_timeline': forms.Select(choices=[
                ('Immediate (Within 7 days)', 'Immediate (Within 7 days)'),
                ('Within 15 days', 'Within 15 days'),
                ('Within 1 month', 'Within 1 month'),
                ('Regular Monthly Requirement', 'Regular Monthly Requirement'),
            ], attrs={'class': 'form-select'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe your requirements, custom branding, agency logo printing, or sample requests...'}),
        }
