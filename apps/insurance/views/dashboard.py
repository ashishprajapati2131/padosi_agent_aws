from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from apps.agents.models import Agent, AgentLead
from django.contrib.auth.models import User
from django.db.models import Count, F, Q
from apps.admin_panel.models.insurance_approval import AgentApprovalRequest
from django.contrib.auth.views import LoginView
from apps.home.services.portal_messages import PORTAL_INSURANCE, portal_error


class InsuranceLoginView(LoginView):
    """Django LoginView with the agent login's per-IP / per-account brute-force limits."""
    template_name = 'insurance/login.html'
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        from apps.agents.views.auth import check_email_login_throttle, check_login_throttle, get_client_ip
        if not check_login_throttle(get_client_ip(request)) or not check_email_login_throttle(request.POST.get('username', '')):
            portal_error(request, "Too many login attempts. Please try again later.", PORTAL_INSURANCE)
            return self.render_to_response(self.get_context_data(form=self.form_class(request)), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        from apps.agents.views.auth import get_client_ip, record_email_login_failure, record_login_attempt
        record_login_attempt(get_client_ip(self.request))
        record_email_login_failure(self.request.POST.get('username', ''))
        return super().form_invalid(form)

@login_required
def dashboard(request):
    user = request.user
    # Ensure user has insurance profile
    if not hasattr(user, 'insurance_profile'):
        return redirect('/') # Or appropriate generic dashboard
    
    profile = user.insurance_profile
    insurance_id = profile.get_insurance_company_id()

    context = {
        'user': user,
        'profile': profile,
    }

    if profile.is_insurance_manager():
        now = timezone.now()
        trend_months = [now - relativedelta(months=i) for i in range(5, -1, -1)]
        # One aggregate instead of a COUNT per stat / trend month.
        stats = Agent.objects.filter(insurance_id=insurance_id).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status='active')),
            inactive=Count('id', filter=Q(status='inactive')),
            pending_manager=Count('id', filter=Q(status='pending_manager_approval')),
            **{
                f'm{i}': Count('id', filter=Q(created_at__year=m.year, created_at__month=m.month))
                for i, m in enumerate(trend_months)
            },
        )
        total_agents = stats['total']
        active_agents = stats['active']
        inactive_agents = stats['inactive']

        # Real lead count: joins agent_leads → agents on insurance_id (mirrors Laravel)
        total_leads = AgentLead.objects.filter(
            agent__insurance_id=insurance_id
        ).count()

        new_agents_this_month = stats['m5']  # trend_months[-1] is the current month

        pending_status_changes = AgentApprovalRequest.objects.filter(
            insurance_id=insurance_id, status='pending'
        ).count()
        pending_onboardings = stats['pending_manager']
        pending_requests = pending_status_changes + pending_onboardings

        pending_manager_approvals = Agent.objects.filter(
            insurance_id=insurance_id, status='pending_manager_approval'
        ).order_by('-created_at')

        sub_users = User.objects.filter(
            insurance_profile__insurance_parent_id=user.id
        ).order_by('insurance_profile__insurance_sub_role')

        trend_labels = [m.strftime('%b') for m in trend_months]
        trend_data = [stats[f'm{i}'] for i in range(len(trend_months))]

        recent_agents = Agent.objects.filter(
            insurance_id=insurance_id
        ).order_by('-created_at')[:5]

        context.update({
            'totalAgents': total_agents,
            'activeAgents': active_agents,
            'inactiveAgents': inactive_agents,
            'totalLeads': total_leads,
            'newAgentsThisMonth': new_agents_this_month,
            'pendingRequests': pending_requests,
            'trendLabels': trend_labels,
            'trendData': trend_data,
            'recentAgents': recent_agents,
            'pendingManagerApprovals': pending_manager_approvals,
            'subUsers': sub_users,
        })
        return render(request, 'insurance/dashboard.html', context)

    if profile.is_insurance_onboarding():
        stats = Agent.objects.filter(onboarded_by=user.id).aggregate(
            total=Count('id'),
            pending_manager=Count('id', filter=Q(status='pending_manager_approval')),
            pending_payment=Count('id', filter=Q(status='pending_accounts_payment')),
            pending_admin=Count('id', filter=Q(status='pending_admin_approval')),
            active=Count('id', filter=Q(status='active')),
        )
        total_onboarded_by_me = stats['total']
        pending_manager = stats['pending_manager']
        pending_payment = stats['pending_payment']
        pending_admin = stats['pending_admin']
        active_agents = stats['active']

        recent_agents = Agent.objects.filter(onboarded_by=user.id).order_by('-created_at')[:5]

        context.update({
            'totalOnboardedByMe': total_onboarded_by_me,
            'pendingManager': pending_manager,
            'pendingPayment': pending_payment,
            'pendingAdmin': pending_admin,
            'activeAgents': active_agents,
            'recentAgents': recent_agents,
        })
        return render(request, 'insurance/dashboard.html', context)

    if profile.is_insurance_sales():
        active_agents = Agent.objects.filter(insurance_id=insurance_id, status='active').count()
        total_leads = AgentLead.objects.filter(
            agent__insurance_id=insurance_id
        ).count()
        recent_leads = AgentLead.objects.filter(
            agent__insurance_id=insurance_id
        ).select_related('agent').annotate(agent_name=F('agent__fullname')).order_by('-created_at')[:5]

        # Top performing active agents by lead count (mirrors withCount('leads'))
        top_agents = (
            Agent.objects
            .filter(insurance_id=insurance_id, status='active')
            .annotate(leads_count=Count('leads'))
            .order_by('-leads_count')[:5]
        )

        context.update({
            'activeAgents': active_agents,
            'totalLeads': total_leads,
            'recentLeads': recent_leads,
            'topAgents': top_agents,
        })
        return render(request, 'insurance/dashboard.html', context)

    if profile.is_insurance_accounts():
        pending_payments_count = Agent.objects.filter(insurance_id=insurance_id, status='pending_accounts_payment').count()
        processed_payments_count = Agent.objects.filter(insurance_id=insurance_id, payment_recorded_by=user).count()
        recent_payments = Agent.objects.filter(
            insurance_id=insurance_id, payment_recorded_by=user
        ).order_by('-payment_recorded_at')[:5]
        
        pending_payments = Agent.objects.filter(
            insurance_id=insurance_id, status='pending_accounts_payment'
        ).order_by('-created_at')[:5]

        context.update({
            'pendingPaymentsCount': pending_payments_count,
            'processedPaymentsCount': processed_payments_count,
            'recentPayments': recent_payments,
            'pendingPayments': pending_payments,
        })
        return render(request, 'insurance/dashboard.html', context)

    return render(request, 'insurance/dashboard.html', context)
