from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from apps.agents.models import Agent, AgentProfile, AgentSubscription
from django.contrib.auth.models import User
from apps.admin_panel.models.insurance_approval import AgentApprovalRequest
import random, string, logging

logger = logging.getLogger(__name__)

def is_insurance_manager(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_manager()

def is_insurance_onboarding(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_onboarding()

def is_insurance_sales(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_sales()

def is_insurance_accounts(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_accounts()

@login_required
def agents_index(request):
    user = request.user
    if not hasattr(user, 'insurance_profile'):
        return redirect('/')
    
    company_id = user.insurance_profile.get_insurance_company_id()
    
    agents_query = Agent.objects.filter(insurance_id=company_id).select_related('user').prefetch_related('subscriptions')
    
    search = request.GET.get('search')
    if search:
        agents_query = agents_query.filter(
            Q(fullname__icontains=search) | 
            Q(email__icontains=search) | 
            Q(mobile__icontains=search)
        ) # Additional fields can be added using Q objects

    if is_insurance_sales(user):
        agents_query = agents_query.filter(status='active')
    else:
        status_filter = request.GET.get('status')
        if status_filter and status_filter != 'all':
            agents_query = agents_query.filter(status=status_filter)

    agents = agents_query.order_by('-created_at')

    # Django paginator could be added here
    context = {'agents': agents}
    return render(request, 'insurance/agents/index.html', context)

@login_required
def agents_create(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user)):
        return redirect('insurance:agents_index')

    request.session.pop('current_agent_id', None)
    
    context = {
        'agent': None,
        'isVerified': False,
        'verifiedEmail': ''
    }
    return render(request, 'insurance/agents/create.html', context)

@login_required
def agents_store(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user)):
        return redirect('insurance:agents_index')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                fullname = request.POST.get('fullname')
                email = request.POST.get('email')
                mobile = request.POST.get('mobile')
                plan_type = request.POST.get('plan_type')

                # Basic creation logic
                new_user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=email,
                    first_name=fullname,
                    is_active=False
                )

                company_id = user.insurance_profile.get_insurance_company_id()
                agent_status = 'pending_manager_approval' if is_insurance_onboarding(user) else 'pending_accounts_payment'

                agent = Agent.objects.create(
                    user=new_user,
                    insurance_id=company_id,
                    onboarded_by=user,
                    fullname=fullname,
                    email=email,
                    mobile=mobile,
                    status=agent_status,
                    plan_type=plan_type,
                    registration_step=2,
                )

                AgentProfile.objects.create(
                    agent=agent,
                    address='Pincode: ' + request.POST.get('agent_pincode', ''),
                    state=request.POST.get('state', ''),
                )

                amount = 8258 if plan_type == 'professional' else 2359
                plan_name = "Professional's Plan" if plan_type == 'professional' else "Starter's Plan"

                AgentSubscription.objects.create(
                    agent=agent,
                    selected_plan=plan_name,
                    registration_amount=amount,
                    payment_status='pending',
                    status='inactive',
                    starts_at=timezone.now(),
                    expires_at=timezone.now() + timezone.timedelta(days=365),
                    razorpay_order_id='INSURANCE_MANUAL_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
                )

                msg = f"Agent {fullname} has been registered and submitted."
                messages.success(request, msg)
                return redirect('insurance:agents_index')
                
        except Exception as e:
            logger.error(f'Insurance agent onboarding failed: {e}')
            messages.error(request, f'Failed to onboard agent: {e}')
            return redirect('insurance:agents_create')

    return redirect('insurance:agents_create')

@login_required
def agents_show(request, agent_id):
    user = request.user
    company_id = user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)
    
    pending_request = AgentApprovalRequest.objects.filter(
        agent=agent, status='pending'
    ).first()

    context = {
        'agent': agent,
        'leads': [], # Lead logic omitted as model not found
        'pendingRequest': pending_request
    }
    return render(request, 'insurance/agents/show.html', context)

@login_required
def request_status_change(request, agent_id):
    user = request.user
    company_id = user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason')
        
        if AgentApprovalRequest.objects.filter(agent=agent, status='pending').exists():
            messages.error(request, 'A pending request already exists.')
            return redirect('insurance:agents_show', agent_id=agent.id)
            
        AgentApprovalRequest.objects.create(
            agent=agent,
            action=action,
            reason=reason,
            status='pending',
            # Assuming these fields are available in admin_panel's AgentApprovalRequest
        )
        
        messages.success(request, 'Your request has been submitted to admin for approval.')

    return redirect('insurance:agents_show', agent_id=agent.id)

# Bulk Cart Methods
@login_required
def add_to_cart(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user)):
        return JsonResponse({'success': False, 'message': 'Unauthorized.'}, status=403)

    if request.method == 'POST':
        # Cart logic using session
        cart = request.session.get('insurance_bulk_cart', [])
        email = request.POST.get('email')
        
        if any(item.get('email') == email for item in cart):
            return JsonResponse({'success': False, 'errors': {'email': ['Email already in cart.']}}, status=422)
            
        if User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'errors': {'email': ['Email already registered.']}}, status=422)

        plan_type = request.POST.get('plan_type')
        amount = 8258 if plan_type == 'professional' else 2359
        
        cart_item = {
            'fullname': request.POST.get('fullname'),
            'email': email,
            'mobile': request.POST.get('mobile'),
            'plan_type': plan_type,
            'amount': amount,
            'agent_pincode': request.POST.get('agent_pincode'),
            'state': request.POST.get('state'),
        }
        
        cart.append(cart_item)
        request.session['insurance_bulk_cart'] = cart
        
        return JsonResponse({
            'success': True,
            'message': 'Agent added to cart successfully!',
            'cart': cart,
            'total_count': len(cart),
            'subtotal': sum(item['amount'] for item in cart)
        })

@login_required
def remove_from_cart(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user)):
        return JsonResponse({'success': False, 'message': 'Unauthorized.'}, status=403)

    if request.method == 'POST':
        email = request.POST.get('email')
        cart = request.session.get('insurance_bulk_cart', [])
        cart = [item for item in cart if item['email'] != email]
        request.session['insurance_bulk_cart'] = cart
        
        return JsonResponse({
            'success': True,
            'message': 'Agent removed from cart successfully!',
            'cart': cart,
            'total_count': len(cart),
            'subtotal': sum(item['amount'] for item in cart)
        })

@login_required
def clear_cart(request):
    request.session.pop('insurance_bulk_cart', None)
    return JsonResponse({'success': True, 'message': 'Cart cleared successfully!'})

@login_required
def checkout_cart(request):
    # Minimal port of the checkout cart functionality
    # In real world, this would create all agents in cart and handle offline payment marking.
    return JsonResponse({'success': True, 'test_payment': True})

