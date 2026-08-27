from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.models import User as DjangoUser, Group
from django.views.decorators.csrf import csrf_exempt
from password_hashing import check_password_hash
from apps.admin_panel.models import User as LaravelUser
from apps.home.services.portal_messages import PORTAL_DISTRIBUTOR, portal_error, portal_success


def distributor_logout(request):
    logout(request)
    portal_success(request, "You have been logged out successfully.", PORTAL_DISTRIBUTOR)
    return redirect('distributors:login')


@csrf_exempt
def distributor_login(request):
    if request.user.is_authenticated and request.user.groups.filter(name='distributor').exists():
        return redirect('distributors:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        laravel_user = LaravelUser.objects.filter(email=email).first()

        if laravel_user:
            if laravel_user.role == 'distributor':
                hash_to_check = laravel_user.password
                is_valid = check_password_hash(password, hash_to_check)

                if is_valid:
                    name_parts = laravel_user.fullname.strip().split(' ', 1)
                    first_name = name_parts[0]
                    last_name = name_parts[1] if len(name_parts) > 1 else ''

                    django_user, created = DjangoUser.objects.get_or_create(
                        username=email,
                        defaults={'email': email, 'first_name': first_name, 'last_name': last_name}
                    )
                    if not created:
                        django_user.first_name = first_name
                        django_user.last_name = last_name
                        django_user.save(update_fields=['first_name', 'last_name'])

                    dist_group, _ = Group.objects.get_or_create(name='distributor')
                    django_user.groups.add(dist_group)

                    login(request, django_user)
                    return redirect('distributors:dashboard')
                else:
                    portal_error(request, "Invalid credentials.", PORTAL_DISTRIBUTOR)
            else:
                portal_error(
                    request,
                    f"Access denied. This account has the role '{laravel_user.role}', not 'distributor'.",
                    PORTAL_DISTRIBUTOR,
                )
        else:
            portal_error(request, "Invalid credentials. User not found.", PORTAL_DISTRIBUTOR)

    return render(request, 'distributors/login.html')
