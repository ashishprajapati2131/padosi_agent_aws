import json
import logging
from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseForbidden

from password_hashing import hash_password, check_password_hash
from apps.distributors.models import SubDistributor
from apps.distributors.views.dashboard import is_distributor
from apps.distributors.views.agents import _distributor_laravel_id
from apps.agents.models import Agent, AgentDraft
from apps.admin_panel.models.referral_code import ReferralCode
from apps.admin_panel.models import User as LaravelUser

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Decorators
# ─────────────────────────────────────────────────────────────────────────────

def sub_distributor_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        sub_dist_id = request.session.get('sub_distributor_id')
        if not sub_dist_id:
            return redirect('distributors:sub_distributor_login')
        
        sub_dist = SubDistributor.objects.filter(id=sub_dist_id).first()
        if not sub_dist or sub_dist.status != 'active':
            request.session.flush()
            messages.error(request, "Your account is not active or has been suspended. Please contact your distributor.")
            return redirect('distributors:sub_distributor_login')
            
        request.sub_distributor = sub_dist
        return view_func(request, *args, **kwargs)
    return _wrapped


# ─────────────────────────────────────────────────────────────────────────────
# 1. Main Distributor Views (Management of Sub-Distributors)
# ─────────────────────────────────────────────────────────────────────────────

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def sub_distributors_index(request):
    """
    Distributor console to manage sub-distributors, view invite link, and track analytics.
    """
    distributor_id = _distributor_laravel_id(request)
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', 'all')

    query = Q(distributor_id=distributor_id)
    if search:
        query &= (Q(fullname__icontains=search) | Q(email__icontains=search) | Q(mobile__icontains=search) | Q(code__icontains=search))
    if status and status != 'all':
        query &= Q(status=status)

    sub_dists_qs = SubDistributor.objects.filter(query).order_by('-created_at')

    # Get distributor's referral code for sub-distributor invite link
    ref_code_obj = ReferralCode.objects.filter(distributor_id=distributor_id).first()
    dist_code = ref_code_obj.code if ref_code_obj else f"DIST{distributor_id}"
    
    sub_invite_url = request.build_absolute_uri(reverse('distributors:sub_distributor_join', args=[dist_code]))

    # Compute overall stats
    total_sub_dists = SubDistributor.objects.filter(distributor_id=distributor_id).count()
    active_sub_dists = SubDistributor.objects.filter(distributor_id=distributor_id, status='active').count()

    total_sub_agents = Agent.objects.filter(distributor_id=distributor_id, sub_distributor_id__isnull=False).count()
    active_sub_agents = Agent.objects.filter(distributor_id=distributor_id, sub_distributor_id__isnull=False, status='active').count()

    # Annotate counts for each sub-distributor
    sub_dist_list = []
    for sd in sub_dists_qs:
        agent_link = request.build_absolute_uri(reverse('agents:referral_join', args=[sd.code]))
        total_ag = Agent.objects.filter(sub_distributor_id=sd.id).count()
        active_ag = Agent.objects.filter(sub_distributor_id=sd.id, status='active').count()
        pending_ag = Agent.objects.filter(sub_distributor_id=sd.id).exclude(status='active').count()
        
        sub_dist_list.append({
            'obj': sd,
            'total_agents': total_ag,
            'active_agents': active_ag,
            'pending_agents': pending_ag,
            'agent_link': agent_link,
        })

    paginator = Paginator(sub_dist_list, 15)
    page_number = request.GET.get('page')
    sub_distributors = paginator.get_page(page_number)

    whatsapp_invite_msg = f"Join my network as a Sub-Distributor on PadosiAgent! Register here: {sub_invite_url}"

    # Portal login link that the distributor shares with EXISTING sub-distributors
    # so they can sign in with their registered email/mobile + password.
    sub_login_url = request.build_absolute_uri(reverse('distributors:sub_distributor_login'))
    whatsapp_login_msg = (
        f"Login to your PadosiAgent Sub-Distributor portal here: {sub_login_url}\n"
        f"Use your registered email/mobile and password."
    )

    context = {
        'sub_distributors': sub_distributors,
        'sub_invite_url': sub_invite_url,
        'whatsapp_invite_msg': whatsapp_invite_msg,
        'sub_login_url': sub_login_url,
        'whatsapp_login_msg': whatsapp_login_msg,
        'total_sub_dists': total_sub_dists,
        'active_sub_dists': active_sub_dists,
        'total_sub_agents': total_sub_agents,
        'active_sub_agents': active_sub_agents,
        'dist_code': dist_code,
    }
    return render(request, 'distributors/sub_distributors/index.html', context)


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def sub_distributor_create(request):
    """
    Distributor directly adds a sub-distributor under their account.
    """
    if request.method != 'POST':
        return redirect('distributors:sub_distributors_index')

    distributor_id = _distributor_laravel_id(request)

    fullname = request.POST.get('fullname', '').strip()
    email = request.POST.get('email', '').strip().lower()
    mobile = request.POST.get('mobile', '').strip()
    password = request.POST.get('password', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not fullname or not email or not mobile or not password:
        messages.error(request, "All fields (Name, Email, Mobile, Password) are required.")
        return redirect('distributors:sub_distributors_index')

    if SubDistributor.objects.filter(email=email).exists():
        messages.error(request, f"A sub-distributor with email '{email}' already exists.")
        return redirect('distributors:sub_distributors_index')

    code = SubDistributor.generate_unique_code(distributor_id, fullname)
    hashed_pwd = hash_password(password)

    SubDistributor.objects.create(
        distributor_id=distributor_id,
        fullname=fullname,
        email=email,
        mobile=mobile,
        password=hashed_pwd,
        code=code,
        notes=notes,
        status='active'
    )

    messages.success(request, f"Sub-Distributor '{fullname}' created successfully with code: {code}!")
    return redirect('distributors:sub_distributors_index')


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def sub_distributor_toggle_status(request, pk):
    """
    Toggle sub-distributor status between active and suspended.
    """
    distributor_id = _distributor_laravel_id(request)
    sub_dist = get_object_or_404(SubDistributor, pk=pk, distributor_id=distributor_id)

    if sub_dist.status == 'active':
        sub_dist.status = 'suspended'
        msg = f"Sub-Distributor '{sub_dist.fullname}' has been suspended."
    else:
        sub_dist.status = 'active'
        msg = f"Sub-Distributor '{sub_dist.fullname}' has been activated."

    sub_dist.save(update_fields=['status', 'updated_at'])
    messages.success(request, msg)
    return redirect('distributors:sub_distributors_index')


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def sub_distributor_agents(request, pk):
    """
    View all agents recruited by this specific sub-distributor.
    """
    distributor_id = _distributor_laravel_id(request)
    sub_dist = get_object_or_404(SubDistributor, pk=pk, distributor_id=distributor_id)

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', 'all')
    plan = request.GET.get('plan', 'all')

    query = Q(sub_distributor_id=sub_dist.id)
    if search:
        query &= (Q(fullname__icontains=search) | Q(email__icontains=search) | Q(mobile__icontains=search))
    if status and status != 'all':
        query &= Q(status=status)
    if plan and plan != 'all':
        if plan == 'starter':
            query &= Q(subscriptions__selected_plan__icontains='starter', subscriptions__status='active')
        elif plan == 'professional':
            query &= Q(subscriptions__selected_plan__icontains='professional', subscriptions__status='active')

    agents_qs = Agent.objects.filter(query).select_related('user').annotate(leads_count=Count('leads')).order_by('-created_at').distinct()

    paginator = Paginator(agents_qs, 15)
    page_number = request.GET.get('page')
    agents = paginator.get_page(page_number)

    agent_link = request.build_absolute_uri(reverse('agents:referral_join', args=[sub_dist.code]))

    context = {
        'sub_dist': sub_dist,
        'agents': agents,
        'agent_link': agent_link,
        'total_count': Agent.objects.filter(sub_distributor_id=sub_dist.id).count(),
        'active_count': Agent.objects.filter(sub_distributor_id=sub_dist.id, status='active').count(),
    }
    return render(request, 'distributors/sub_distributors/agents.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Public Candidate Join (Invited to be a Sub-Distributor)
# ─────────────────────────────────────────────────────────────────────────────

def sub_distributor_join(request, dist_code):
    """
    Public registration page for candidates who click a distributor's Sub-Distributor Invite Link.
    URL: /sub-distributor/join/<dist_code>/
    """
    code_val = str(dist_code).strip().upper()
    
    # Resolve parent distributor
    distributor = None
    ref_obj = ReferralCode.objects.filter(code=code_val).first()
    if ref_obj and ref_obj.distributor_id:
        distributor = LaravelUser.objects.filter(id=ref_obj.distributor_id).first()
    elif code_val.startswith('DIST'):
        try:
            dist_id_str = ''.join(filter(str.isdigit, code_val))
            if dist_id_str:
                distributor = LaravelUser.objects.filter(id=int(dist_id_str), role='distributor').first()
        except Exception:
            pass

    if not distributor:
        messages.error(request, "Invalid or expired invitation link.")
        return render(request, 'distributors/sub_distributors/public_join.html', {'error': 'Invalid or expired invitation link.'})

    if request.method == 'POST':
        fullname = request.POST.get('fullname', '').strip()
        email = request.POST.get('email', '').strip().lower()
        mobile = request.POST.get('mobile', '').strip()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        errors = []
        if not fullname:
            errors.append("Full Name is required.")
        if not email:
            errors.append("Email is required.")
        if not mobile:
            errors.append("Mobile Number is required.")
        if not password or len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        if SubDistributor.objects.filter(email=email).exists():
            errors.append(f"An account with email '{email}' already exists. Please log in.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'distributors/sub_distributors/public_join.html', {
                'distributor': distributor,
                'dist_code': code_val,
                'form_data': request.POST
            })

        # Create SubDistributor
        sub_code = SubDistributor.generate_unique_code(distributor.id, fullname)
        hashed_pwd = hash_password(password)

        sub_dist = SubDistributor.objects.create(
            distributor_id=distributor.id,
            fullname=fullname,
            email=email,
            mobile=mobile,
            password=hashed_pwd,
            code=sub_code,
            status='active'
        )

        # Automatically log in the new sub-distributor
        request.session['sub_distributor_id'] = sub_dist.id
        request.session['sub_distributor_name'] = sub_dist.fullname
        request.session['sub_distributor_code'] = sub_dist.code
        request.session['sub_distributor_dist_id'] = sub_dist.distributor_id

        messages.success(request, f"Welcome, {fullname}! Your Sub-Distributor account is ready.")
        return redirect('distributors:sub_distributor_dashboard')

    return render(request, 'distributors/sub_distributors/public_join.html', {
        'distributor': distributor,
        'dist_code': code_val
    })


# ─────────────────────────────────────────────────────────────────────────────
# 3. Sub-Distributor Dedicated Portal
# ─────────────────────────────────────────────────────────────────────────────

def sub_distributor_login(request):
    """
    Sub-Distributor Portal Login page.
    """
    if request.session.get('sub_distributor_id'):
        return redirect('distributors:sub_distributor_dashboard')

    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip().lower()
        password = request.POST.get('password', '')

        sub_dist = SubDistributor.objects.filter(
            Q(email=identifier) | Q(mobile=identifier)
        ).first()

        if sub_dist:
            if sub_dist.status != 'active':
                messages.error(request, "Your account is inactive or suspended. Please contact your distributor.")
                return render(request, 'distributors/sub_distributors/portal_login.html')

            if check_password_hash(password, sub_dist.password):
                request.session['sub_distributor_id'] = sub_dist.id
                request.session['sub_distributor_name'] = sub_dist.fullname
                request.session['sub_distributor_code'] = sub_dist.code
                request.session['sub_distributor_dist_id'] = sub_dist.distributor_id

                sub_dist.last_login_at = timezone.now()
                sub_dist.save(update_fields=['last_login_at'])

                messages.success(request, f"Welcome back, {sub_dist.fullname}!")
                return redirect('distributors:sub_distributor_dashboard')
            else:
                messages.error(request, "Invalid credentials.")
        else:
            messages.error(request, "No account found with this email or mobile number.")

    return render(request, 'distributors/sub_distributors/portal_login.html')


def sub_distributor_logout(request):
    """
    Logout from Sub-Distributor Portal.
    """
    request.session.pop('sub_distributor_id', None)
    request.session.pop('sub_distributor_name', None)
    request.session.pop('sub_distributor_code', None)
    request.session.pop('sub_distributor_dist_id', None)
    messages.success(request, "You have been logged out successfully.")
    return redirect('distributors:sub_distributor_login')


@sub_distributor_required
def sub_distributor_dashboard(request):
    """
    Dedicated lightweight Sub-Distributor Portal Dashboard:
    - View and copy exclusive Agent Registration Link
    - Quick WhatsApp share
    - Register new agent button
    - List of agents registered under this Sub-Distributor
    """
    sub_dist = request.sub_distributor
    agent_link = request.build_absolute_uri(reverse('agents:referral_join', args=[sub_dist.code]))

    whatsapp_msg = (
        f"Hi! Partner with PadosiAgent to expand your insurance agency network and get genuine client inquiries.\n\n"
        f"Register your profile using my official registration link below:\n{agent_link}\n\n"
        f"Let me know if you need any assistance with registration!"
    )

    # Agents recruited by this sub-distributor
    agents_qs = Agent.objects.filter(sub_distributor_id=sub_dist.id).select_related('user').order_by('-created_at')
    
    total_agents = agents_qs.count()
    active_agents = agents_qs.filter(status='active').count()
    pending_agents = agents_qs.filter(status__in=['pending_approval', 'pending_payment', 'incomplete']).count()

    # Drafts
    from apps.agents.models import AgentDraft
    agent_emails = set(agents_qs.values_list('email', flat=True))
    draft_count = AgentDraft.objects.filter(sub_distributor_id=sub_dist.id, registration_step__gte=1).exclude(email__in=agent_emails).count()

    total_with_drafts = total_agents + draft_count

    # Parent Distributor Info
    parent_dist = LaravelUser.objects.filter(id=sub_dist.distributor_id).first()

    context = {
        'sub_dist': sub_dist,
        'parent_dist': parent_dist,
        'agent_link': agent_link,
        'whatsapp_msg': whatsapp_msg,
        'total_agents': total_with_drafts,
        'active_agents': active_agents,
        'pending_agents': pending_agents,
        'clicks': sub_dist.clicks,
        'agents': agents_qs[:50],
    }
    return render(request, 'distributors/sub_distributors/portal_dashboard.html', context)


@sub_distributor_required
def sub_distributor_register_agent(request):
    """
    Sub-distributor clicks 'Register Agent' to onboard an agent on their behalf.
    Pre-configures the session with sub_distributor_id and distributor_id.
    """
    sub_dist = request.sub_distributor

    # Clear previous registration draft session
    request.session.pop('current_draft_id', None)
    request.session.pop('email_verified', None)
    request.session.pop('verified_email', None)
    request.session.pop('reg_step', None)

    # Tag registration with both parent distributor and sub-distributor
    request.session['distributor_id'] = sub_dist.distributor_id
    request.session['sub_distributor_id'] = sub_dist.id
    request.session['ref_code'] = sub_dist.code
    request.session['distributor_led_registration'] = True

    from apps.agents.views.registration import _get_registration_context
    context = _get_registration_context(request)
    context['sub_distributor_onboarding'] = True
    context['sub_distributor_name'] = sub_dist.fullname

    return render(request, 'agents/registration.html', context)
