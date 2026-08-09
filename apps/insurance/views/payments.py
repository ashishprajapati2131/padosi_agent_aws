from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.agents.models import Agent, AgentSubscription
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.conf import settings
from django.db import transaction
import random, string

# Optional razorpay import
try:
    import razorpay
except ImportError:
    razorpay = None

from apps.insurance.decorators import insurance_manager_or_accounts_required

@login_required
@insurance_manager_or_accounts_required
def payments_index(request):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agents = Agent.objects.filter(
        insurance_id=company_id,
        status='pending_accounts_payment'
    ).prefetch_related('subscriptions').order_by('-created_at')

    return render(request, 'insurance/payments/index.html', {'agents': agents})

@login_required
@insurance_manager_or_accounts_required
def record_payment(request, agent_id):

    messages.error(request, 'Offline payment is disabled. Please pay online via Razorpay.')
    return redirect('insurance:payments_index')

@login_required
@insurance_manager_or_accounts_required
def create_razorpay_order(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    subscription = agent.subscriptions.filter(payment_status='pending').order_by('-created_at').first()
    amount = subscription.registration_amount if subscription else (2359 if agent.plan_type == 'starter' else 8258)
    
    key = getattr(settings, 'RAZORPAY_KEY', '')
    secret = getattr(settings, 'RAZORPAY_SECRET', '')
    is_test_key = key.startswith('rzp_test')

    order_id = None
    if key and secret and razorpay:
        client = razorpay.Client(auth=(key, secret))
        order_data = {
            'amount': int(amount * 100),
            'currency': 'INR',
            'receipt': f'agent_ins_{agent.id}_{int(timezone.now().timestamp())}',
            'payment_capture': 1,
            'notes': {
                'agent_id': agent.id,
                'insurance_user_id': request.user.id,
            }
        }
        try:
            razorpay_order = client.order.create(data=order_data)
            order_id = razorpay_order['id']
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Razorpay API failure: {str(e)}'}, status=500)
    elif not is_test_key and key:
        return JsonResponse({'success': False, 'message': 'Payment gateway keys are not configured.'}, status=500)

    return JsonResponse({
        'success': True,
        'order_id': order_id,
        'amount': int(amount * 100),
        'key': key,
        'name': request.user.first_name,
        'email': request.user.email,
        'test_payment': is_test_key or not key,
    })

@login_required
@insurance_manager_or_accounts_required
def handle_payment_success(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    is_test_payment = request.POST.get('test_payment') == '1'
    payment_ref = request.POST.get('razorpay_payment_id')
    order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')
    
    key = getattr(settings, 'RAZORPAY_KEY', '')
    secret = getattr(settings, 'RAZORPAY_SECRET', '')

    if not is_test_payment and key and secret and razorpay:
        client = razorpay.Client(auth=(key, secret))
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_ref,
                'razorpay_signature': signature
            })
            
            subscription = agent.subscriptions.filter(payment_status='pending').order_by('-created_at').first()
            amount = subscription.registration_amount if subscription else (2359 if agent.plan_type == 'starter' else 8258)
            expected_amount_paise = int(amount * 100)
            
            razorpay_payment = client.payment.fetch(payment_ref)
            if int(razorpay_payment['amount']) != expected_amount_paise:
                return JsonResponse({'success': False, 'message': 'Payment amount mismatch.'}, status=400)
                
        except razorpay.errors.SignatureVerificationError:
            return JsonResponse({'success': False, 'message': 'Invalid payment signature.'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Failed to verify payment: {str(e)}'}, status=400)

    if not payment_ref:
        payment_ref = 'TEST_PAY_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

    try:
        with transaction.atomic():
            # Refresh from DB with lock
            agent = Agent.objects.select_for_update().get(id=agent.id)
            if agent.status in ['pending_admin_approval', 'active']:
                return JsonResponse({'success': True, 'redirect_url': '/insurance/payments/'})
            
            agent.status = 'pending_admin_approval'
            agent.payment_method = 'Razorpay (Online)'
            agent.payment_reference = payment_ref
            # Missing in model but needed in logic, handled generically.
            agent.save()

            subscription = agent.subscriptions.filter(payment_status='pending').order_by('-created_at').select_for_update().first()
            if subscription:
                subscription.payment_status = 'completed'
                subscription.razorpay_payment_id = payment_ref
                subscription.starts_at = timezone.now()
                subscription.expires_at = timezone.now() + timezone.timedelta(days=365)
                subscription.save()

        return JsonResponse({
            'success': True,
            'message': 'Online payment completed successfully. Agent has been advanced to admin approval.',
            'redirect_url': '/insurance/payments/'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Payment handling failed: {str(e)}'}, status=500)
