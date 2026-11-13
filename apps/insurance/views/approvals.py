from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.agents.models import Agent
from apps.insurance.decorators import insurance_manager_required

@login_required
@insurance_manager_required
def approvals_index(request):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agents = Agent.objects.filter(
        insurance_id=company_id,
        status='pending_manager_approval'
    ).select_related('onboarded_by').prefetch_related('subscriptions').order_by('-created_at')

    return render(request, 'insurance/approvals/index.html', {'agents': agents})

@login_required
@insurance_manager_required
def approvals_approve(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    if request.method == 'POST':
        if agent.status != 'pending_manager_approval':
            messages.error(request, 'This agent is not awaiting manager approval.')
            return redirect('insurance:approvals_index')
        agent.status = 'pending_accounts_payment'
        agent.save()
        messages.success(request, f"Agent {agent.fullname}'s onboarding request has been approved and moved to the accounts payment queue.")
    
    return redirect('insurance:approvals_index')

@login_required
@insurance_manager_required
def approvals_reject(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    if request.method == 'POST':
        if agent.status != 'pending_manager_approval':
            messages.error(request, 'This agent is not awaiting manager approval.')
            return redirect('insurance:approvals_index')
        rejection_reason = request.POST.get('rejection_reason')
        if not rejection_reason:
            messages.error(request, 'Rejection reason is required.')
            return redirect('insurance:approvals_index')

        agent.status = 'rejected'
        # Keep the manager's reason for the admin team (audit INS4); admin_notes is shown in admin.
        from datetime import datetime
        note = f"[{datetime.now():%Y-%m-%d %H:%M}] Insurance manager rejected: {rejection_reason.strip()[:1000]}"
        agent.admin_notes = f"{agent.admin_notes}\n{note}".strip() if agent.admin_notes else note
        agent.save()
        messages.success(request, f"Agent {agent.fullname}'s onboarding request has been rejected.")
    
    return redirect('insurance:approvals_index')
