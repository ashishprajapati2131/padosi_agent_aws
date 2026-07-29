from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash

@login_required
def profile_edit(request):
    user = request.user
    
    if request.method == 'POST':
        fullname = request.POST.get('fullname')
        current_password = request.POST.get('current_password')
        password = request.POST.get('password')
        password_confirmation = request.POST.get('password_confirmation')

        if not fullname:
            messages.error(request, 'Fullname is required.')
            return redirect('insurance:profile')

        if password:
            if not current_password:
                messages.error(request, 'Current password is required to change password.')
                return redirect('insurance:profile')
            
            if not user.check_password(current_password):
                messages.error(request, 'The current password is incorrect.')
                return redirect('insurance:profile')
            
            if len(password) < 8:
                messages.error(request, 'The password must be at least 8 characters.')
                return redirect('insurance:profile')
            
            if password != password_confirmation:
                messages.error(request, 'The password confirmation does not match.')
                return redirect('insurance:profile')
            
            user.set_password(password)
            update_session_auth_hash(request, user) # Prevent logout

        user.first_name = fullname # Assuming fullname maps to first_name or a custom profile field
        user.save()
        
        messages.success(request, 'Profile updated successfully.')
        return redirect('insurance:profile')

    return render(request, 'insurance/profile.html', {'insurance': user})
