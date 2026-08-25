import json
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.models import User as DjangoUser, Group
from password_hashing import check_password_hash

def distributor_logout(request):
    logout(request)
    return redirect('distributors:login')
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from apps.admin_panel.models import User as LaravelUser

@csrf_exempt
def distributor_login(request):
    if request.user.is_authenticated and request.user.groups.filter(name='distributor').exists():
        return redirect('distributors:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        
        # Authenticate against the legacy Laravel 'users' table
        laravel_user = LaravelUser.objects.filter(email=email).first()
        
        if laravel_user:
            if laravel_user.role == 'distributor':
                hash_to_check = laravel_user.password
                is_valid = check_password_hash(password, hash_to_check)

                if is_valid:
                    # Authentication successful! 
                    # Sync with Django's auth system so sessions/decorators work seamlessly.
                    name_parts = laravel_user.fullname.strip().split(' ', 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ''

                    django_user, created = DjangoUser.objects.get_or_create(
                        username=email, 
                        defaults={'email': email, 'first_name': first_name, 'last_name': last_name}
                    )
                    if not created:
                        # Sync name on every login
                        django_user.first_name = first_name
                        django_user.last_name = last_name
                        django_user.save(update_fields=['first_name', 'last_name'])
                    
                    dist_group, _ = Group.objects.get_or_create(name='distributor')
                    django_user.groups.add(dist_group)
                    
                    # Log them into Django
                    login(request, django_user)
                    return redirect('distributors:dashboard')
                else:
                    messages.error(request, "Invalid credentials.")
            else:
                messages.error(request, f"Access denied. This account has the role '{laravel_user.role}', not 'distributor'.")
        else:
            messages.error(request, "Invalid credentials. User not found.")
            
    return render(request, 'distributors/login.html')
