"""
Wholesaler Registration and Verification Forms.
"""
from django import forms
from django.contrib.auth.models import User
from apps.wholesale.models.profile import WholesalerProfile, BusinessVerificationDocument

class WholesalerAccountForm(forms.Form):
    """Step 1: Account credentials and contact person."""
    full_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': 'e.g. Ramesh Patel'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-control', 'placeholder': 'business@company.com'
    }))
    phone = forms.CharField(max_length=15, widget=forms.TextInput(attrs={
        'class': 'form-control', 'placeholder': '10-digit mobile number'
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control', 'placeholder': 'Choose a secure password'
    }))
    password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control', 'placeholder': 'Confirm your password'
    }))

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password_confirm')
        if p1 and p2 and p1 != p2:
            self.add_error('password_confirm', "Passwords do not match.")
        return cleaned_data


class WholesalerBusinessForm(forms.ModelForm):
    """Step 2: Business details and tax credentials."""
    class Meta:
        model = WholesalerProfile
        fields = [
            'business_name', 'business_type', 'description', 'website',
            'address', 'city', 'state', 'pincode', 'gstin', 'pan_number',
            'business_registration_no'
        ]
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Shree Ram Enterprises LLP'}),
            'business_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe your products and manufacturing/stocking capability'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yourwebsite.com'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Street address, Industrial area / GIDC'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Ahmedabad'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Gujarat'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '380001'}),
            'gstin': forms.TextInput(attrs={'class': 'form-control text-uppercase', 'placeholder': '24AAAAA0000A1Z5'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control text-uppercase', 'placeholder': 'AAAAA0000A'}),
            'business_registration_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MSME / Udyam / CIN'}),
        }


class DocumentUploadForm(forms.Form):
    """Step 3: Verification document file upload."""
    gst_certificate = forms.FileField(required=False, widget=forms.FileInput(attrs={
        'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'
    }))
    business_registration = forms.FileField(required=False, widget=forms.FileInput(attrs={
        'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'
    }))
    pan_card = forms.FileField(required=False, widget=forms.FileInput(attrs={
        'class': 'form-control', 'accept': '.pdf,.jpg,.jpeg,.png'
    }))
