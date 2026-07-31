from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from apps.distributors.views.dashboard import is_distributor
from apps.agents.models import Agent
from apps.admin_panel.models.referral_code import ReferralCode
from apps.agents.views.registration import agent_registration

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_index(request):
    from apps.admin_panel.models import User as LaravelUser
    from django.db.models import Count, Q
    from django.core.paginator import Paginator
    l_user = LaravelUser.objects.filter(email=request.user.email).first()
    distributor_id = l_user.id if l_user else request.user.id

    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', 'all')
    plan = request.GET.get('plan', 'all')

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

    agents_list = Agent.objects.filter(query).select_related('user').annotate(leads_count=Count('leads')).order_by('-created_at').distinct()
    
    paginator = Paginator(agents_list, 15)
    page_number = request.GET.get('page')
    agents = paginator.get_page(page_number)
    
    # Check for referral code
    referral_code = ReferralCode.objects.filter(distributor_id=distributor_id).first()
    
    return render(request, 'distributors/agents/index.html', {
        'agents': agents,
        'referralCode': referral_code
    })

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_create(request):
    from apps.admin_panel.models import User as LaravelUser
    l_user = LaravelUser.objects.filter(email=request.user.email).first()
    distributor_id = l_user.id if l_user else request.user.id
    # Clear any previous draft session
    request.session.pop('current_draft_id', None)
    request.session.pop('email_verified', None)
    request.session.pop('verified_email', None)
    request.session.pop('reg_step', None)

    # Set the distributor's referral code into the session so it automatically applies
    # during the agent registration flow
    referral_code = ReferralCode.objects.filter(distributor_id=distributor_id).first()
    if referral_code:
        request.session['applied_promo_code'] = referral_code.code
        
    return agent_registration(request)

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_store(request):
    # The registration flow routes to its own step-by-step URLs.
    # This is just a fallback.
    return redirect('distributors:agents_index')

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def agents_show(request, pk):
    from apps.admin_panel.models import User as LaravelUser
    l_user = LaravelUser.objects.filter(email=request.user.email).first()
    distributor_id = l_user.id if l_user else request.user.id

    try:
        agent = Agent.objects.select_related('user', 'activeSubscription').get(pk=pk, distributor_id=distributor_id)
    except Agent.DoesNotExist:
        return redirect('distributors:agents_index')
        
    return render(request, 'distributors/agents/show.html', {
        'agent': agent
    })
