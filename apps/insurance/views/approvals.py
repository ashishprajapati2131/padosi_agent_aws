from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.agents.models import Agent
from django.http import HttpResponseForbidden
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
        rejection_reason = request.POST.get('rejection_reason')
        if not rejection_reason:
            messages.error(request, 'Rejection reason is required.')
            return redirect('insurance:approvals_index')

        agent.status = 'rejected'
        agent.save()
        
        # Here we could also log the reason to a separate model if needed.
        messages.success(request, f"Agent {agent.fullname}'s onboarding request has been rejected.")
    
    return redirect('insurance:approvals_index')
