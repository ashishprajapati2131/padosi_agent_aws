from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.agents.models import Agent
# Optional imports for notification models
try:
    from apps.agents.models import AgentNotification, AgentDeviceToken
except ImportError:
    AgentNotification = None
    AgentDeviceToken = None

import logging
logger = logging.getLogger(__name__)

@login_required
def notify_form(request):
    user = request.user
    if not hasattr(user, 'insurance_profile'):
        return redirect('/')

    company_id = user.insurance_profile.get_insurance_company_id()
    
    agents = Agent.objects.filter(
        insurance_id=company_id,
        status='active'
    ).order_by('fullname')

    token_count = 0
    push_agents = []

    if AgentDeviceToken:
        # Complex queries simplified for brevity
        token_count = AgentDeviceToken.objects.filter(
            agent__insurance_id=company_id,
            agent__status='active'
        ).values('agent_id').distinct().count()

        # Group by agent logic would go here

    context = {
        'agents': agents,
        'tokenCount': token_count,
        'pushAgents': push_agents,
    }
    return render(request, 'insurance/notify.html', context)

@login_required
def notify_send(request):
    user = request.user
    if not hasattr(user, 'insurance_profile'):
        return redirect('/')

    if request.method == 'POST':
        agent_id = request.POST.get('agent_id')
        title = request.POST.get('title')
        body = request.POST.get('body')

        company_id = user.insurance_profile.get_insurance_company_id()
        agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

        if AgentNotification:
            AgentNotification.objects.create(
                agent=agent,
                title=title,
                body=body
            )

        # Send FCM push if the agent has device tokens (mirrors InsuranceNotificationController)
        try:
            if AgentDeviceToken:
                tokens = list(
                    AgentDeviceToken.objects
                    .filter(agent_id=agent.id)
                    .exclude(token__isnull=True)
                    .exclude(token='')
                    .values_list('token', flat=True)
                    .distinct()
                )
                if tokens:
                    from apps.admin_panel.services.fcm import FcmService
                    FcmService().send_to_tokens(tokens, title, body, {
                        'type': 'insurance_notification',
                        'sender': user.get_full_name() or user.username,
                    })
        except Exception as exc:
            logger.warning(f"FCM push notify failed for agent #{agent.id}: {exc}")
        
        logger.info(f"Insurance user #{user.id} sent notification to agent #{agent.id} ({agent.fullname})")
        messages.success(request, f"Notification sent successfully to {agent.fullname}!")

    return redirect('insurance:notify_form')
