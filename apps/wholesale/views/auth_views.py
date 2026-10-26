"""
Wholesaler Authentication and Multi-Step Registration Views.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.db import transaction
from apps.wholesale.forms.registration_forms import (
    WholesalerAccountForm, WholesalerBusinessForm, DocumentUploadForm
)
from apps.wholesale.models.profile import WholesalerProfile, BusinessVerificationDocument
from apps.wholesale.adapters.auth_bridge import is_wholesale_admin, safe_next_url

def wholesaler_login_view(request):
    """
    Dedicated Login view strictly for Wholesalers and Suppliers.
    Guards against role leakage:
    - If user is already logged in as Wholesaler -> Wholesaler Dashboard.
    - If user is logged in as Agent -> Redirect to Agent Dashboard.
    - If user is logged in as Distributor -> Redirect to Distributor Cross-Sell.
    - If user is Admin -> Wholesale Approvals.
    """
    if hasattr(request, 'user') and request.user.is_authenticated:
        if hasattr(request.user, 'wholesaler_profile'):
            return redirect('wholesale:wholesaler_dashboard')
        if hasattr(request.user, 'agent') or getattr(request.user, 'role', '') == 'agent':
            messages.info(request, "You are logged in as an Agent. Redirected to your Agent Dashboard.")
            return redirect('/agent/dashboard/?tab=marketplace')
        if request.user.groups.filter(name='distributor').exists() or getattr(request.user, 'role', '') == 'distributor':
            messages.info(request, "You are logged in as a Distributor. Redirected to your Distributor Portal.")
            return redirect('distributors:cross_sell')
        if is_wholesale_admin(request):
            return redirect('wholesale:admin_approvals')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        from apps.agents.views.auth import (
            check_email_login_throttle, check_login_throttle, get_client_ip,
            record_email_login_failure, record_login_attempt,
        )
        ip = get_client_ip(request)
        # Same brute-force limits as the agent login (per IP and per account).
        if not check_login_throttle(ip) or not check_email_login_throttle(email):
            messages.error(request, "Too many login attempts. Please try again later.")
            return render(request, 'wholesale/wholesaler/login.html', status=429)

        user = User.objects.filter(email=email).first()
        if user:
            user = authenticate(request, username=user.username, password=password)
            
        if user is not None:
            # Check role: Is this account a wholesaler?
            if hasattr(user, 'wholesaler_profile'):
                login(request, user)
                messages.success(request, f"Welcome back, {user.wholesaler_profile.business_name}!")
                return redirect(safe_next_url(request, request.GET.get('next'), 'wholesale:wholesaler_dashboard'))
            elif is_wholesale_admin(request) or user.is_staff or user.is_superuser:
                login(request, user)
                messages.success(request, f"Welcome back, Admin {user.username}!")
                return redirect('wholesale:admin_approvals')
            elif hasattr(user, 'agent'):
                login(request, user)
                messages.info(request, "This account is registered as an Insurance Agent. Redirecting to your Agent Dashboard.")
                return redirect('/agent/dashboard/?tab=marketplace')
            elif user.groups.filter(name='distributor').exists():
                login(request, user)
                messages.info(request, "This account is registered as a Distributor. Redirecting to your Distributor Portal.")
                return redirect('distributors:cross_sell')
            else:
                messages.error(request, "This account does not have an active Wholesaler profile. Please register below as a supplier.")
        else:
            record_login_attempt(ip)
            record_email_login_failure(email)
            messages.error(request, "Invalid business email or password.")

    return render(request, 'wholesale/wholesaler/login.html')


def wholesaler_logout_view(request):
    """Logout view for wholesalers: cleanly clears session and returns to login."""
    from apps.agents.views.auth import _is_cross_site_get
    if _is_cross_site_get(request):
        return redirect('wholesale:wholesaler_dashboard')
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('wholesale:wholesaler_login')





def wholesaler_register_view(request):
    """
    Multi-step registration wizard:
    Step 1: Account credentials
    Step 2: Business & GST information
    Step 3: Verification documents
    """
    if hasattr(request, 'user') and request.user.is_authenticated and hasattr(request.user, 'wholesaler_profile'):
        return redirect('wholesale:wholesaler_dashboard')

    account_form = WholesalerAccountForm(request.POST or None)
    business_form = WholesalerBusinessForm(request.POST or None)
    doc_form = DocumentUploadForm(request.POST or None, request.FILES or None)

    if request.method == 'POST':
        if account_form.is_valid() and business_form.is_valid() and doc_form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Create Django User
                    acc_data = account_form.cleaned_data
                    username = acc_data['email']
                    user = User.objects.create_user(
                        username=username,
                        email=acc_data['email'],
                        password=acc_data['password'],
                        first_name=acc_data['full_name']
                    )

                    # 2. Create WholesalerProfile
                    profile = business_form.save(commit=False)
                    profile.user = user
                    profile.contact_person = acc_data['full_name']
                    profile.phone = acc_data['phone']
                    profile.email = acc_data['email']
                    profile.verification_status = 'SUBMITTED'
                    profile.save()

                    # 3. Handle KYC Documents
                    if request.FILES.get('gst_certificate'):
                        BusinessVerificationDocument.objects.create(
                            wholesaler=profile,
                            document_type='GST_CERT',
                            document_file=request.FILES['gst_certificate'],
                            document_number=profile.gstin
                        )
                    if request.FILES.get('business_registration'):
                        BusinessVerificationDocument.objects.create(
                            wholesaler=profile,
                            document_type='BUSINESS_REG',
                            document_file=request.FILES['business_registration'],
                            document_number=profile.business_registration_no
                        )
                    if request.FILES.get('pan_card'):
                        BusinessVerificationDocument.objects.create(
                            wholesaler=profile,
                            document_type='PAN_CARD',
                            document_file=request.FILES['pan_card'],
                            document_number=profile.pan_number
                        )

                    # Log the user in
                    login(request, user)
                    messages.success(
                        request,
                        "Registration submitted successfully! Your business verification is under review by our admin team."
                    )
                    return redirect('wholesale:wholesaler_dashboard')

            except Exception as e:
                messages.error(request, f"Registration failed: {str(e)}")

    context = {
        'account_form': account_form,
        'business_form': business_form,
        'doc_form': doc_form,
    }
    return render(request, 'wholesale/wholesaler/register.html', context)
