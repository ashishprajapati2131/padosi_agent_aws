from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from apps.agents.models import Agent, AgentLead
from django.contrib.auth.models import User
from django.db.models import Count, F
from apps.admin_panel.models.insurance_approval import AgentApprovalRequest

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
        total_agents = Agent.objects.filter(insurance_id=insurance_id).count()
        active_agents = Agent.objects.filter(insurance_id=insurance_id, status='active').count()
        inactive_agents = Agent.objects.filter(insurance_id=insurance_id, status='inactive').count()

        # Real lead count: joins agent_leads → agents on insurance_id (mirrors Laravel)
        total_leads = AgentLead.objects.filter(
            agent__insurance_id=insurance_id
        ).count()
        
        now = timezone.now()
        new_agents_this_month = Agent.objects.filter(
            insurance_id=insurance_id, 
            created_at__year=now.year,
            created_at__month=now.month
        ).count()

        pending_status_changes = AgentApprovalRequest.objects.filter(
            insurance_id=insurance_id, status='pending'
        ).count()
        pending_onboardings = Agent.objects.filter(
            insurance_id=insurance_id, status='pending_manager_approval'
        ).count()
        pending_requests = pending_status_changes + pending_onboardings

        pending_manager_approvals = Agent.objects.filter(
            insurance_id=insurance_id, status='pending_manager_approval'
        ).order_by('-created_at')

        sub_users = User.objects.filter(
            insurance_profile__insurance_parent_id=user.id
        ).order_by('insurance_profile__insurance_sub_role')

        trend_labels = []
        trend_data = []
        for i in range(5, -1, -1):
            month_date = now - relativedelta(months=i)
            trend_labels.append(month_date.strftime('%b'))
            count = Agent.objects.filter(
                insurance_id=insurance_id,
                created_at__year=month_date.year,
                created_at__month=month_date.month
            ).count()
            trend_data.append(count)

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
        total_onboarded_by_me = Agent.objects.filter(onboarded_by=user.id).count()
        pending_manager = Agent.objects.filter(onboarded_by=user.id, status='pending_manager_approval').count()
        pending_payment = Agent.objects.filter(onboarded_by=user.id, status='pending_accounts_payment').count()
        pending_admin = Agent.objects.filter(onboarded_by=user.id, status='pending_admin_approval').count()
        active_agents = Agent.objects.filter(onboarded_by=user.id, status='active').count()

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
