from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import check_password, make_password
from django.contrib import messages
from apps.distributors.views.dashboard import is_distributor
from django.contrib.auth.models import User

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

        if email and email != user.email:
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                messages.error(request, "Email is already taken.")
                return redirect('distributors:profile')

        user.first_name = fullname # since django User model uses first_name/last_name
        user.email = email
        user.username = email

        if new_password:
            if not current_password:
                messages.error(request, "Current password is required to change password.")
                return redirect('distributors:profile')
            
            if not user.check_password(current_password):
                messages.error(request, "The provided password does not match your current password.")
                return redirect('distributors:profile')

            if new_password != password_confirmation:
                messages.error(request, "Passwords do not match.")
                return redirect('distributors:profile')

            user.set_password(new_password)

        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('distributors:profile')

    return redirect('distributors:profile')
