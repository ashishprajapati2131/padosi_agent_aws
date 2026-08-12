import json
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from apps.agents.models import Agent, AgentLead
from apps.admin_panel.models.referral_code import ReferralCode
from apps.home.models.site_setting import SiteSetting

def is_distributor(user):
    # Depending on how your User model is set up, this checks if the user is a distributor
    # E.g., user.groups.filter(name='distributor').exists() or getattr(user, 'role', '') == 'distributor'
    # We will assume a 'distributor' group or a hasattr check
    if getattr(user, 'role', None) == 'distributor':
        return True
    if user.groups.filter(name='distributor').exists():
        return True
    # If they are superuser they might also access it
    if user.is_superuser:
        return True
    return False

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def dashboard(request):
    distributor = request.user
    from apps.admin_panel.models import User as LaravelUser
    l_user = LaravelUser.objects.filter(email=distributor.email).first()
    distributor_id = l_user.id if l_user else distributor.id
    
    # Ensure distributor has a referral code
    # In PHP: $referralCode = ReferralCode::generateForDistributor($distributor);
    # Let's see if we have generate_for_distributor method. 
    # For now, get or create it.
    referral_code, created = ReferralCode.objects.get_or_create(
        distributor_id=distributor_id,
        defaults={
            'code': f'DIST{distributor_id}{distributor.first_name[:3].upper()}',
            'is_active': True
        }
    )

    now = timezone.now()
    
    # Stats
    total_agents = Agent.objects.filter(distributor_id=distributor_id).count()
    active_agents = Agent.objects.filter(distributor_id=distributor_id, status='active').count()
    
    total_leads = AgentLead.objects.filter(agent__distributor_id=distributor_id).count()
    
    new_agents_this_month = Agent.objects.filter(
        distributor_id=distributor_id,
        created_at__year=now.year,
        created_at__month=now.month
    ).count()

    professional_agents = Agent.objects.filter(
        distributor_id=distributor_id,
        plan_type='professional'
    ).count()

    trend_labels = []
    trend_data = []
    for i in range(5, -1, -1):
        month_date = now - relativedelta(months=i)
        trend_labels.append(month_date.strftime('%b'))
        count = Agent.objects.filter(
            distributor_id=distributor_id,
            created_at__year=month_date.year,
            created_at__month=month_date.month
        ).count()
        trend_data.append(count)

    recent_agents = Agent.objects.filter(
        distributor_id=distributor_id
    ).select_related('user').order_by('-created_at')[:5]

    # referral stats
    # PHP uses $referralCode->convertedUsages()->count()
    # In Django, it would be ReferralUsage.objects.filter(referral_code=referral_code, status='converted').count()
    from apps.admin_panel.models.referral_usage import ReferralUsage
    converted_count = ReferralUsage.objects.filter(
        referral_code_id=referral_code.id, 
        status='converted'
    ).count()

    referral_stats = {
        'clicks': getattr(referral_code, 'clicks', 0),
        'total': getattr(referral_code, 'total_referrals', 0),
        'pending': getattr(referral_code, 'pending_referrals', 0),
        'converted': converted_count,
    }

    referral_url = request.build_absolute_uri(f'/join/{referral_code.code}')
    default_message = f"Hi! I'm partnering with PadosiAgent, and I'd love for you to join my network. Register using my exclusive link below to get special benefits:\n\n{referral_url}\n\nLet me know if you have any questions!"
    
    # Laravel parity: custom invite message (users.custom_invite_message) wins over the admin site setting
    custom_message = l_user.custom_invite_message if l_user else None
    if custom_message:
        raw_message = custom_message
    else:
        try:
            setting = SiteSetting.objects.get(key='distributor_invite_message')
            raw_message = setting.value
        except SiteSetting.DoesNotExist:
            raw_message = default_message

    share_message = raw_message.replace('{LINK}', referral_url)
    
    distributor_first_name = (l_user.fullname if l_user else distributor.first_name).split(' ')[0]

    context = {
        'distributor': distributor,
        'distributorFirstName': distributor_first_name,
        'totalAgents': total_agents,
        'activeAgents': active_agents,
        'totalLeads': total_leads,
        'newAgentsThisMonth': new_agents_this_month,
        'professionalAgents': professional_agents,
        'trendLabels': trend_labels,
        'trendData': trend_data,
        'recentAgents': recent_agents,
        'referralCode': referral_code,
        'referralStats': referral_stats,
        'referralUrl': referral_url,
        'shareMessage': share_message,
    }
    return render(request, 'distributors/dashboard.html', context)

@login_required(login_url='distributors:login')
@user_passes_test(is_distributor, login_url='distributors:login')
def save_invite_message(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            msg = data.get('custom_invite_message', '')

            # Persist to the Laravel users table row (mirrors PHP: $distributor->custom_invite_message = ...)
            from apps.admin_panel.models import User as LaravelUser

            l_user = LaravelUser.objects.filter(email=request.user.email).first()
            if l_user is None:
                LaravelUser.objects.create(
                    fullname=request.user.first_name or request.user.username,
                    email=request.user.email,
                    password=request.user.password or '',
                    role='distributor',
                    status='active',
                    custom_invite_message=msg,
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )
            else:
                l_user.custom_invite_message = msg
                l_user.updated_at = timezone.now()
                l_user.save()

            return JsonResponse({'success': True, 'message': 'Your custom invitation message has been saved successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
    return JsonResponse({'success': False}, status=405)
