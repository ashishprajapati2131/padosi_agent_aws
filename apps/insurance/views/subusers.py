from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from apps.insurance.models import InsuranceProfile
from django.http import HttpResponseForbidden

def is_insurance_manager(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_manager()

@login_required
def subusers_index(request):
    if not is_insurance_manager(request.user):
        return HttpResponseForbidden("Unauthorized")

    sub_users = User.objects.filter(
        insurance_profile__insurance_parent_id=request.user.id
    ).select_related('insurance_profile').order_by('-date_joined')

    # Define roles dictionary as it was in the Laravel template
    roles = {
        'manager': {
            'title': 'Co-Manager / Super User',
            'icon': 'fa-user-tie',
            'desc': 'Has full management rights, including agent approval and sub-user controls.',
            'color': 'blue',
        },
        'onboarding': {
            'title': 'Onboarding & Ops (Sub-User 1)',
            'icon': 'fa-user-plus',
            'desc': 'Responsible for agent registrations and submitting plans for approval.',
            'color': 'blue',
        },
        'sales': {
            'title': 'Sales Team (Sub-User 2)',
            'icon': 'fa-chart-line',
            'desc': 'Monitors leads, coordinates with agents, and sends push notifications.',
            'color': 'purple',
        },
        'accounts': {
            'title': 'Accounts & Finance (Sub-User 3)',
            'icon': 'fa-file-invoice-dollar',
            'desc': 'Handles plan payment validation and records reference information.',
            'color': 'green',
        }
    }

    roles_list = []
    for key, info in roles.items():
        # Find the subuser that has this role
        matched_user = None
        for su in sub_users:
            if hasattr(su, 'insurance_profile') and su.insurance_profile and su.insurance_profile.insurance_sub_role == key:
                matched_user = su
                break
                
        roles_list.append({
            'key': key,
            'info': info,
            'user': matched_user
        })

    return render(request, 'insurance/subusers/index.html', {'roles_list': roles_list})

@login_required
def subusers_store(request):
    if not is_insurance_manager(request.user):
        return HttpResponseForbidden("Unauthorized")

    if request.method == 'POST':
        fullname = request.POST.get('fullname')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirmation = request.POST.get('password_confirmation')
        insurance_sub_role = request.POST.get('insurance_sub_role')

        # Validation
        if not all([fullname, email, password, password_confirmation, insurance_sub_role]):
            messages.error(request, 'All fields are required.')
            return redirect('insurance:subusers_index')

        if password != password_confirmation:
            messages.error(request, 'Passwords do not match.')
            return redirect('insurance:subusers_index')

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return redirect('insurance:subusers_index')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'A user with this email already exists.')
            return redirect('insurance:subusers_index')

        if insurance_sub_role not in dict(InsuranceProfile.SUB_ROLE_CHOICES).keys():
            messages.error(request, 'Invalid sub-role selected.')
            return redirect('insurance:subusers_index')

        existing = User.objects.filter(
            insurance_profile__insurance_parent_id=request.user.id,
            insurance_profile__insurance_sub_role=insurance_sub_role
        ).first()

        if existing:
            messages.error(request, f"A sub-user with the '{insurance_sub_role.capitalize()}' role already exists.")
            return redirect('insurance:subusers_index')

        # Create user
        sub_user = User.objects.create_user(
            username=email, # Using email as username
            email=email,
            password=password,
            first_name=fullname,
            is_active=True
        )

        # Create profile
        InsuranceProfile.objects.create(
            user=sub_user,
            insurance_parent_id=request.user.id,
            insurance_sub_role=insurance_sub_role
        )

        messages.success(request, 'Sub-user created successfully.')
    
    return redirect('insurance:subusers_index')

@login_required
def subusers_reset_password(request, user_id):
    if not is_insurance_manager(request.user):
        return HttpResponseForbidden("Unauthorized")

    if request.method == 'POST':
        sub_user = get_object_or_404(User, id=user_id, insurance_profile__insurance_parent_id=request.user.id)
        password = request.POST.get('password')
        password_confirmation = request.POST.get('password_confirmation')

        if not password or password != password_confirmation:
            messages.error(request, 'Passwords do not match or are missing.')
            return redirect('insurance:subusers_index')

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return redirect('insurance:subusers_index')

        sub_user.set_password(password)
        sub_user.save()

        messages.success(request, f"Password for {sub_user.first_name} has been reset successfully.")

    return redirect('insurance:subusers_index')

@login_required
def subusers_toggle_status(request):
    if not is_insurance_manager(request.user):
        return HttpResponseForbidden("Unauthorized")

    if request.method == 'POST':
        user_id = request.POST.get('id')
        if not user_id:
            messages.error(request, 'User ID is required.')
            return redirect('insurance:subusers_index')

        sub_user = get_object_or_404(User, id=user_id, insurance_profile__insurance_parent_id=request.user.id)
        
        # Toggle status
        sub_user.is_active = not sub_user.is_active
        sub_user.save()

        status_label = 'enabled' if sub_user.is_active else 'disabled'
        messages.success(request, f"Sub-user {sub_user.first_name} has been {status_label}.")

    return redirect('insurance:subusers_index')
