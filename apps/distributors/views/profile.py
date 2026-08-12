from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from apps.distributors.views.dashboard import is_distributor
from django.contrib.auth.models import User
from apps.admin_panel.models import User as LaravelUser
import bcrypt

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def profile_edit(request):
    user = request.user
    return render(request, 'distributors/profile.html', {'user': user})

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def profile_update(request):
    user = request.user
    if request.method == 'POST':
        fullname = request.POST.get('fullname')
        email = request.POST.get('email')
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('password')
        password_confirmation = request.POST.get('password_confirmation')

        # Get corresponding Laravel user
        laravel_user = LaravelUser.objects.filter(email=user.email).first()

        if email and email != user.email:
            if User.objects.filter(email=email).exclude(id=user.id).exists() or \
               LaravelUser.objects.filter(email=email).exclude(id=laravel_user.id if laravel_user else 0).exists():
                messages.error(request, "Email is already taken.")
                return redirect('distributors:profile')

        name_parts = fullname.strip().split(' ', 1)
        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        user.email = email
        user.username = email

        if new_password:
            if not current_password:
                messages.error(request, "Current password is required to change password.")
                return redirect('distributors:profile')
            
            # Check against Django password
            if not user.check_password(current_password):
                # Fallback: check against Laravel password in case it was synced manually
                if laravel_user and not bcrypt.checkpw(current_password.encode('utf-8'), laravel_user.password.replace('$2y$', '$2a$').encode('utf-8')):
                    messages.error(request, "The provided password does not match your current password.")
                    return redirect('distributors:profile')

            if new_password != password_confirmation:
                messages.error(request, "Passwords do not match.")
                return redirect('distributors:profile')

            user.set_password(new_password)
            
            # Hash password for Laravel
            salt = bcrypt.gensalt()
            bcrypt_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
            laravel_hashed_password = bcrypt_hash.replace('$2b$', '$2y$', 1)
            
            if laravel_user:
                laravel_user.password = laravel_hashed_password

        user.save()
        
        # Sync changes to Laravel user
        if laravel_user:
            laravel_user.fullname = fullname
            laravel_user.email = email
            laravel_user.save()
            
        messages.success(request, 'Profile updated successfully.')
        return redirect('distributors:profile')

    return redirect('distributors:profile')
