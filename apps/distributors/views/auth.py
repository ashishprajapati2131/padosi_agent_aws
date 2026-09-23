from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.models import User as DjangoUser, Group
from password_hashing import check_password_hash
from apps.admin_panel.models import User as LaravelUser
from apps.home.services.portal_messages import PORTAL_DISTRIBUTOR, portal_error, portal_success


def distributor_logout(request):
    logout(request)
    portal_success(request, "You have been logged out successfully.", PORTAL_DISTRIBUTOR)
    return redirect('distributors:login')


def distributor_login(request):
    if request.user.is_authenticated and request.user.groups.filter(name='distributor').exists():
        return redirect('distributors:dashboard')

    if request.method == 'POST':
        from apps.agents.views.auth import (
            check_email_login_throttle,
            check_login_throttle,
            get_client_ip,
            record_email_login_failure,
            record_login_attempt,
        )

        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        ip = get_client_ip(request)

        # Same brute-force limits as the agent login (per IP and per account).
        if not check_login_throttle(ip) or not check_email_login_throttle(email):
            portal_error(request, "Too many login attempts. Please try again later.", PORTAL_DISTRIBUTOR)
            return render(request, 'distributors/login.html')

        laravel_user = LaravelUser.objects.filter(email=email).first()
        # Verify the password BEFORE revealing anything about the account: the
        # old flow disclosed "not found" vs. the account's role for any email.
        password_ok = bool(laravel_user) and check_password_hash(password, laravel_user.password)

        if not password_ok:
            record_login_attempt(ip)
            record_email_login_failure(email)
            portal_error(request, "Invalid credentials.", PORTAL_DISTRIBUTOR)
        elif laravel_user.role != 'distributor':
            # Correct password but not a distributor: point them to their own
            # portal without echoing the stored role.
            portal_error(
                request,
                "This account is not a distributor account. Please use the correct login page.",
                PORTAL_DISTRIBUTOR,
            )
        else:
            from django.core.cache import cache
            from apps.agents.views.auth import _email_throttle_key
            cache.delete(_email_throttle_key(email))

            name_parts = (laravel_user.fullname or email).strip().split(' ', 1)
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

    return render(request, 'distributors/login.html')
