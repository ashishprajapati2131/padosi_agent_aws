import re
import random
import string
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.db import transaction

from apps.distributors.views.dashboard import is_distributor
from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.admin_panel.models.referral_code import ReferralCode
from apps.admin_panel.models.referral_usage import ReferralUsage
from apps.agents.views.registration import ALL_INDIAN_STATES

logger = logging.getLogger(__name__)


def _distributor_laravel_id(request):
    """Mirror PHP auth()->id(): the distributor's row id in the shared Laravel 'users' table."""
    from apps.admin_panel.models import User as LaravelUser
    l_user = LaravelUser.objects.filter(email=request.user.email).first()
    return l_user.id if l_user else request.user.id


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_index(request):
    from django.db.models import Count, Q
    from django.core.paginator import Paginator
    distributor_id = _distributor_laravel_id(request)

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', 'all')
    plan = request.GET.get('plan', 'all')
    sub_dist_filter = request.GET.get('sub_distributor', 'all')

    query = Q(distributor_id=distributor_id)
    if search:
        query &= (Q(fullname__icontains=search) | Q(email__icontains=search) | Q(mobile__icontains=search))

    if status and status != 'all':
        query &= Q(status=status)

    if plan and plan != 'all':
        if plan == 'starter':
            query &= Q(subscriptions__selected_plan__icontains='starter', subscriptions__status='active')
        elif plan == 'professional':
            query &= Q(subscriptions__selected_plan__icontains='professional', subscriptions__status='active')

    if sub_dist_filter and sub_dist_filter != 'all':
        if sub_dist_filter == 'direct':
            query &= Q(sub_distributor_id__isnull=True)
        elif sub_dist_filter.isdigit():
            query &= Q(sub_distributor_id=int(sub_dist_filter))

    # PHP parity: paginate(10)
    agents_list_qs = Agent.objects.filter(query).select_related('user').annotate(leads_count=Count('leads')).order_by('-created_at').distinct()

    # Fetch AgentDrafts
    from apps.agents.models import AgentDraft
    from apps.distributors.models import SubDistributor
    
    drafts_query = Q(distributor_id=distributor_id, registration_step__gte=1)
    if search:
        drafts_query &= (Q(fullname__icontains=search) | Q(email__icontains=search) | Q(mobile__icontains=search))
    if sub_dist_filter and sub_dist_filter != 'all':
        if sub_dist_filter == 'direct':
            drafts_query &= Q(sub_distributor_id__isnull=True)
        elif sub_dist_filter.isdigit():
            drafts_query &= Q(sub_distributor_id=int(sub_dist_filter))
        
    if status and status != 'all' and status not in ['draft', 'claim', 'incomplete', 'pending_payment']:
        drafts = []
    elif plan and plan != 'all':
        drafts = []
    else:
        drafts = list(AgentDraft.objects.filter(drafts_query).order_by('-created_at'))

    agent_emails = set(agents_list_qs.values_list('email', flat=True))
    
    class MockDraftAgent:
        def __init__(self, draft):
            self.id = draft.id
            self.fullname = draft.fullname
            self.email = draft.email
            self.mobile = draft.mobile
            self.status = 'claim' if draft.registration_step >= 2 else 'draft'
            self.activeSubscription = None
            self.leads_count = 0
            self.created_at = draft.created_at
            self.is_draft = True
            self.sub_distributor_id = getattr(draft, 'sub_distributor_id', None)
            self.sub_distributor = SubDistributor.objects.filter(id=draft.sub_distributor_id).first() if draft.sub_distributor_id else None

    combined_list = list(agents_list_qs)
    for d in drafts:
        if d.email not in agent_emails:
            combined_list.append(MockDraftAgent(d))
            
    combined_list.sort(key=lambda x: x.created_at, reverse=True)

    paginator = Paginator(combined_list, 10)
    page_number = request.GET.get('page')
    agents = paginator.get_page(page_number)

    # Check for referral code
    referral_code = ReferralCode.objects.filter(distributor_id=distributor_id).first()
    sub_distributors = SubDistributor.objects.filter(distributor_id=distributor_id).order_by('fullname')

    return render(request, 'distributors/agents/index.html', {
        'agents': agents,
        'referralCode': referral_code,
        'subDistributors': sub_distributors,
        'selectedSubDist': sub_dist_filter,
    })


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_create(request):
    """
    Quick agent onboarding (mirrors PHP DistributorAgentController::create).
    Clears session state and redirects to the main public registration form.
    """
    # Clear any previous registration draft session
    request.session.pop('current_draft_id', None)
    request.session.pop('email_verified', None)
    request.session.pop('verified_email', None)
    request.session.pop('reg_step', None)
    
    # Indicate that a distributor is initiating the registration
    request.session['distributor_led_registration'] = True

    # Render directly to keep the URL at /distributor/agents/create/ (mirroring PHP)
    from apps.agents.views.registration import _get_registration_context
    context = _get_registration_context(request)
    return render(request, 'agents/registration.html', context)



@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_show(request, pk):
    distributor_id = _distributor_laravel_id(request)

    try:
        # PHP parity: eager load user/profile/leads/profileViews
        # (activeSubscription is a property — accessed via the model, not select_related)
        agent = Agent.objects.select_related('user', 'profile').prefetch_related(
            'leads', 'profile_views'
        ).get(pk=pk, distributor_id=distributor_id)
    except Agent.DoesNotExist:
        return redirect('distributors:agents_index')

    return render(request, 'distributors/agents/show.html', {
        'agent': agent
    })


@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_resume_payment(request, pk):
    """
    Allow the distributor to resume payment for an agent whose payment failed.
    """
    distributor_id = _distributor_laravel_id(request)

    try:
        agent = Agent.objects.get(
            pk=pk, 
            distributor_id=distributor_id, 
            status__in=['pending_payment', 'incomplete']
        )
    except Agent.DoesNotExist:
        messages.error(request, "Agent not found or payment already completed.")
        return redirect('distributors:agents_index')

    from apps.agents.models import AgentDraft
    session_key = request.session.session_key
    if not session_key:
        request.session.create()
        session_key = request.session.session_key

    draft = AgentDraft.objects.filter(email=agent.email).first()
    if not draft:
        draft = AgentDraft.objects.create(
            session_key=session_key,
            email=agent.email,
            fullname=agent.fullname,
            mobile=agent.mobile,
            agent_pincode=agent.agent_pincode,
            experience_range=agent.experience_range,
            client_base=agent.client_base,
            email_verified=True,
            registration_step=2
        )
        # Carry over additional fields
        draft.insurance_companies = agent.insurance_companies
        draft.segments = list(agent.segments.values_list('segment_type', flat=True))
        
        try:
            profile = agent.profile
            draft.license_number = profile.license_number
            draft.license_valid_till = profile.license_valid_till
            draft.pan_number = profile.pan_number
            draft.arn_number = profile.arn_number
            draft.euin_number = profile.euin_number
            draft.investment_valid_till = profile.investment_valid_till
            draft.investment_types = profile.investment_types
            draft.software_name = profile.software_name
            if profile.portfolio_breakdown:
                draft.life_insurance = profile.portfolio_breakdown.get('life_insurance', 0)
                draft.health_insurance = profile.portfolio_breakdown.get('health_insurance', 0)
                draft.general_insurance = profile.portfolio_breakdown.get('general_insurance', 0)
                draft.motor = profile.portfolio_breakdown.get('motor', 0)
            draft.desired_services = profile.desired_services
        except Exception:
            pass

        draft.save()

    request.session['current_draft_id'] = draft.pk
    request.session['reg_step'] = 3
    request.session['distributor_led_registration'] = True

    return redirect('/chooseplan/')