from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib import messages
from django.views.decorators.http import require_POST
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.admin_auth import Admin
from apps.admin_panel import registry
from apps.admin_panel.services import admins_service

def get_permissions_list():
    """Permission checkboxes for the admin editor (declared in apps/admin_panel/registry.py)."""
    return registry.permission_choices()


def admins_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    query = Admin.objects.all()

    # Search filter
    search = request.GET.get('search', '').strip()
    if search:
        query = query.filter(name__icontains=search) | query.filter(email__icontains=search)

    # Role filter
    role = request.GET.get('role', 'all').strip()
    if role != 'all':
        query = query.filter(role=role)

    query = query.order_by('-created_at')

    # Paginate by 15
    paginator = Paginator(query, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'admin/admins/index.html', {
        'admins': page_obj,
        'search': search,
        'selected_role': role
    })

def admins_create(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    permissions = get_permissions_list()
    return render(request, 'admin/admins/create.html', {
        'permissionsList': permissions
    })

def admins_store(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirmation = request.POST.get('password_confirmation', '')
        role = request.POST.get('role', '').strip()
        permissions_selected = request.POST.getlist('permissions[]') or request.POST.getlist('permissions')

        if not name or not email or not password or not role:
            messages.error(request, 'All fields are required.')
            return redirect('admin_admins_create')

        if password != password_confirmation:
            messages.error(request, 'Passwords do not match.')
            return redirect('admin_admins_create')

        if len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return redirect('admin_admins_create')

        if Admin.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return redirect('admin_admins_create')

        admins_service.create_admin(name, email, password, role, permissions_selected)

        messages.success(request, 'Administrator created successfully.')
        return redirect('admin_admins_index')

    return redirect('admin_admins_index')

def admins_edit(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin = get_object_or_404(Admin, id=id)
    permissions = get_permissions_list()
    selected_perms = admin.permissions if isinstance(admin.permissions, list) else []
    return render(request, 'admin/admins/edit.html', {
        'admin': admin,
        'permissionsList': permissions,
        'selectedPermissions': selected_perms
    })

def admins_update(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect('admin_login')

    admin = get_object_or_404(Admin, id=id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirmation = request.POST.get('password_confirmation', '')
        role = request.POST.get('role', '').strip()
        permissions_selected = request.POST.getlist('permissions[]') or request.POST.getlist('permissions')

        if not name or not email or not role:
            messages.error(request, 'Name, email, and role are required.')
            return redirect('admin_admins_edit', id=id)

        if password:
            if password != password_confirmation:
                messages.error(request, 'Passwords do not match.')
                return redirect('admin_admins_edit', id=id)
            if len(password) < 8:
                messages.error(request, 'Password must be at least 8 characters long.')
                return redirect('admin_admins_edit', id=id)

        if Admin.objects.filter(email=email).exclude(id=id).exists():
            messages.error(request, 'Email already exists.')
            return redirect('admin_admins_edit', id=id)

        from apps.admin_panel.views.dashboard import ADMIN_SESSION_COOKIE
        current = request.COOKIES.get(ADMIN_SESSION_COOKIE) or ''
        # Revokes the admin's other sessions when the password changes.
        admins_service.update_admin(admin, name, email, password, role, permissions_selected, current)

        messages.success(request, 'Administrator updated successfully.')
        return redirect('admin_admins_index')

    return redirect('admin_admins_index')

@require_POST
def admins_destroy(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)

    if admin_id == id:
        return JsonResponse({'success': False, 'message': 'Unauthorized. You cannot delete your own administrator account.'}, status=403)

    admin = get_object_or_404(Admin, id=id)
    admins_service.delete_admin(admin)

    return JsonResponse({'success': True, 'message': 'Administrator deleted successfully.'})
