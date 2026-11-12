from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.conf import settings
from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.agents.services.feature_unlock import PLAN_LABELS
from django.contrib.auth.models import User
from apps.admin_panel.models.insurance_approval import AgentApprovalRequest
from padosi_agent.razorpay_env import USER_PAYMENT_UNAVAILABLE
from apps.insurance.models import InsuranceBulkOrder
from apps.insurance.views.payments import InsurancePaymentRejected, captured_insurance_payment
import random, string, logging, datetime

logger = logging.getLogger(__name__)

def is_insurance_manager(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_manager()

def is_insurance_onboarding(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_onboarding()

def is_insurance_sales(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_sales()

def is_insurance_accounts(user):
    return hasattr(user, 'insurance_profile') and user.insurance_profile.is_insurance_accounts()

def get_or_sync_insurance_company_id(user):
    """
    Ensures that the insurance company ID exists in the Laravel `users` table
    to prevent foreign key constraint violations when creating agents.
    """
    company_id = user.insurance_profile.get_insurance_company_id()
    from apps.admin_panel.models.users import User as LaravelUser
    from django.contrib.auth.models import User as AuthUser
    
    if not LaravelUser.objects.filter(id=company_id).exists():
        auth_user = AuthUser.objects.get(id=company_id)
        LaravelUser.objects.create(
            id=company_id,
            fullname=auth_user.first_name or auth_user.username,
            email=auth_user.email,
            password=auth_user.password,
            role='insurance',
            status='active'
        )
    return company_id

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
    
    import json
    cart = request.session.get('insurance_bulk_cart', [])
    
    context = {
        'agent': None,
        'isVerified': False,
        'verifiedEmail': '',
        'initial_cart_json': json.dumps(cart)
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

                company_id = get_or_sync_insurance_company_id(user)
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
                plan_name = PLAN_LABELS['professional'] if plan_type == 'professional' else PLAN_LABELS['starter']

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
            if e.__class__.__name__ == 'IntegrityError':
                messages.error(request, 'Failed to onboard agent: Could not link the agent to your insurance profile. Ensure your account is fully set up.')
            else:
                messages.error(request, 'Failed to onboard agent. Please ensure all details are correct and try again.')
            return redirect('insurance:agents_create')

    return redirect('insurance:agents_create')

@login_required
def agents_show(request, agent_id):
    user = request.user
    if not hasattr(user, 'insurance_profile'):
        return redirect('/')
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
    if not hasattr(user, 'insurance_profile'):
        return redirect('/')
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
    return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)

@login_required
def remove_from_cart(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        cart = request.session.get('insurance_bulk_cart', [])
        cart = [item for item in cart if item.get('email') != email]
        request.session['insurance_bulk_cart'] = cart
        return JsonResponse({
            'success': True,
            'message': 'Agent removed from cart successfully!',
            'cart': cart,
            'total_count': len(cart),
            'subtotal': sum(item['amount'] for item in cart)
        })
    return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)

@login_required
def clear_cart(request):
    request.session.pop('insurance_bulk_cart', None)
    return JsonResponse({'success': True, 'message': 'Cart cleared successfully!'})

@login_required
def checkout_cart(request):
    user = request.user
    # Laravel parity: manager / onboarding / accounts operate the cart; sales kept for existing behaviour
    if not (is_insurance_manager(user) or is_insurance_onboarding(user) or is_insurance_sales(user) or is_insurance_accounts(user)):
        return JsonResponse({'success': False, 'message': 'Unauthorized.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    cart = request.session.get('insurance_bulk_cart', [])
    if not cart:
        return JsonResponse({'success': False, 'message': 'Your cart is empty.'}, status=400)

    payment_type = request.POST.get('payment_type') # 'offline' or 'approval'
    payment_method = request.POST.get('payment_method', '').strip()
    payment_reference = request.POST.get('payment_reference', '').strip()
    payment_recorded_at = request.POST.get('payment_recorded_at', '').strip()

    if payment_type == 'offline' and not (is_insurance_manager(user) or is_insurance_accounts(user)):
        return JsonResponse({'success': False, 'message': 'Only the manager or accounts sub-user can record offline payments.'}, status=403)

    recorded_dt = None
    ALLOWED_METHODS = {'NEFT', 'IMPS', 'UPI', 'Cheque', 'Cash', 'Bank Transfer', 'Other'}
    if payment_type == 'offline':
        if not payment_method:
            return JsonResponse({'success': False, 'message': 'Payment method is required for offline payment.'}, status=400)
        if payment_method not in ALLOWED_METHODS:
            return JsonResponse({'success': False, 'message': 'Choose a valid payment method.'}, status=400)
        if not payment_reference:
            return JsonResponse({'success': False, 'message': 'Transaction reference / UTR is required for offline payment.'}, status=400)
        # Writing a Razorpay-looking id into razorpay_order_id unlocked the dashboard as if paid
        # online. record_payment already blocks this; the cart must too (audit INS1).
        if payment_reference.lower().startswith(('order_', 'pay_')):
            return JsonResponse({'success': False, 'message': 'Enter the bank / UPI / cheque reference here, not a Razorpay id.'}, status=400)
        if not payment_recorded_at:
            return JsonResponse({'success': False, 'message': 'Payment date is required for offline payment.'}, status=400)
        recorded_dt = parse_date(payment_recorded_at)
        if not recorded_dt:
            return JsonResponse({'success': False, 'message': 'Payment date is invalid.'}, status=400)
        if recorded_dt > datetime.date.today():
            return JsonResponse({'success': False, 'message': 'Payment date cannot be in the future.'}, status=400)

    recorded_at = datetime.datetime.combine(recorded_dt, datetime.datetime.min.time()) if recorded_dt else None

    try:
        with transaction.atomic():
            company_id = get_or_sync_insurance_company_id(user)
            
            for item in cart:
                fullname = item.get('fullname')
                email = item.get('email')
                mobile = item.get('mobile')
                plan_type = item.get('plan_type')

                if User.objects.filter(email=email).exists():
                    raise ValueError(f"Email {email} is already registered.")

                new_user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=email,
                    first_name=fullname,
                    is_active=False
                )
                
                agent_status = 'pending_admin_approval' if payment_type == 'offline' else 'pending_manager_approval'

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
                    payment_method=payment_method if payment_type == 'offline' else '',
                    payment_reference=payment_reference if payment_type == 'offline' else '',
                    payment_recorded_at=recorded_at,
                    payment_recorded_by=user if payment_type == 'offline' else None,
                )

                AgentProfile.objects.create(
                    agent=agent,
                    address='Pincode: ' + item.get('agent_pincode', ''),
                    state=item.get('state', ''),
                )

                amount = item.get('amount')
                plan_name = PLAN_LABELS['professional'] if plan_type == 'professional' else PLAN_LABELS['starter']
                
                sub_payment_status = 'completed' if payment_type == 'offline' else 'pending'

                AgentSubscription.objects.create(
                    agent=agent,
                    selected_plan=plan_name,
                    registration_amount=amount,
                    payment_status=sub_payment_status,
                    status='inactive',
                    starts_at=recorded_at if payment_type == 'offline' else None,
                    expires_at=(recorded_at + timezone.timedelta(days=365)) if recorded_at else None,
                    # Never store the UTR in razorpay_order_id: a Razorpay-looking value here
                    # unlocks the dashboard as if paid online (audit INS1).
                    razorpay_order_id='OFFLINE_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10)),
                    razorpay_payment_id=None,
                )

            request.session.pop('insurance_bulk_cart', None)
            
            msg = 'Offline payment recorded successfully!' if payment_type == 'offline' else 'Cart submitted to manager for approval.'
            return JsonResponse({
                'success': True,
                'message': msg,
                'redirect': '/insurance/agents/',
                'redirect_url': '/insurance/agents/'
            })

    except Exception as e:
        logger.exception('Cart checkout failed')
        return JsonResponse(
            {'success': False, 'message': 'Could not record this payment. Please try again.'},
            status=500,
        )

try:
    import razorpay
except ImportError:
    razorpay = None

@login_required
def checkout_online_start(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user) or is_insurance_sales(user)):
        return JsonResponse({'success': False, 'message': 'Unauthorized.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    cart = request.session.get('insurance_bulk_cart', [])
    if not cart:
        return JsonResponse({'success': False, 'message': 'Your cart is empty.'}, status=400)

    total_amount = sum(item.get('amount', 0) for item in cart)

    key = getattr(settings, 'RAZORPAY_KEY', '')
    secret = getattr(settings, 'RAZORPAY_SECRET', '')
    is_test_key = key.startswith('rzp_test')

    order_id = None
    if key and secret and razorpay:
        client = razorpay.Client(auth=(key, secret))
        order_data = {
            'amount': int(total_amount * 100),
            'currency': 'INR',
            'receipt': f'cart_ins_{user.id}_{int(timezone.now().timestamp())}',
            'payment_capture': 1,
            'notes': {
                'insurance_user_id': user.id,
                'cart_size': len(cart)
            }
        }
        try:
            razorpay_order = client.order.create(data=order_data)
            order_id = razorpay_order['id']
            # The webhook / recovery fulfil from this row if the tab closes after payment.
            InsuranceBulkOrder.objects.create(
                razorpay_order_id=order_id,
                created_by=user,
                company_id=get_or_sync_insurance_company_id(user),
                cart=cart,
                amount_paise=int(total_amount * 100),
            )
            request.session['insurance_bulk_order_id'] = order_id
        except Exception as e:
            logger.error('Insurance Razorpay order failed: %s', e)
            return JsonResponse({'success': False, 'message': USER_PAYMENT_UNAVAILABLE}, status=500)
    elif not is_test_key and key:
        return JsonResponse({'success': False, 'message': USER_PAYMENT_UNAVAILABLE}, status=500)

    return JsonResponse({
        'success': True,
        'order_id': order_id,
        'amount': int(total_amount * 100),
        'key': key,
        'name': user.first_name or user.username,
        'email': user.email,
        'test_payment': is_test_key or not key,
    })

def fulfil_insurance_bulk_order(order_id, payment_id, payment=None, signature=None):
    """Create the agents of a captured bulk-cart (``cart_ins_``) order exactly once.

    Shared by the browser callback, the Razorpay webhook and
    recover_orphaned_payments. The cart and amount come from the
    InsuranceBulkOrder row written when the order was created, never from the
    session or the client. Returns (order, fulfilled): fulfilled is False when
    it was already paid. Raises InsurancePaymentRejected.
    """
    from apps.agents.views.registration import _paise_amounts_match

    bulk_order = InsuranceBulkOrder.objects.filter(razorpay_order_id=order_id).first()
    if not bulk_order:
        raise InsurancePaymentRejected('Order not found.')
    if bulk_order.status == 'paid':
        return bulk_order, False

    key = getattr(settings, 'RAZORPAY_KEY', '')
    secret = getattr(settings, 'RAZORPAY_SECRET', '')
    client = razorpay.Client(auth=(key, secret)) if key and secret and razorpay else None
    payment = captured_insurance_payment(client, order_id, payment_id, payment)
    if not _paise_amounts_match(payment.get('amount'), bulk_order.amount_paise):
        logger.error('Insurance bulk order %s - amount mismatch. payment=%s paid=%s expected=%s',
                     order_id, payment_id, payment.get('amount'), bulk_order.amount_paise)
        raise InsurancePaymentRejected('Payment amount mismatch.')

    try:
        with transaction.atomic():
            bulk_order = InsuranceBulkOrder.objects.select_for_update().get(pk=bulk_order.pk)
            if bulk_order.status == 'paid':
                return bulk_order, False  # completed concurrently
            user = bulk_order.created_by
            company_id = bulk_order.company_id

            for item in bulk_order.cart:
                fullname = item.get('fullname')
                email = item.get('email')
                mobile = item.get('mobile')
                plan_type = item.get('plan_type')

                if User.objects.filter(email=email).exists():
                    raise ValueError(f"Email {email} is already registered.")

                new_user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=email,
                    first_name=fullname,
                    is_active=False
                )

                agent = Agent.objects.create(
                    user=new_user,
                    insurance_id=company_id,
                    onboarded_by=user,
                    fullname=fullname,
                    email=email,
                    mobile=mobile,
                    status='pending_admin_approval',
                    plan_type=plan_type,
                    registration_step=2,
                )

                AgentProfile.objects.create(
                    agent=agent,
                    address='Pincode: ' + item.get('agent_pincode', ''),
                    state=item.get('state', ''),
                )

                amount = item.get('amount')
                plan_name = PLAN_LABELS['professional'] if plan_type == 'professional' else PLAN_LABELS['starter']

                AgentSubscription.objects.create(
                    agent=agent,
                    selected_plan=plan_name,
                    registration_amount=amount,
                    payment_status='completed',
                    status='inactive',
                    starts_at=timezone.now(),
                    expires_at=timezone.now() + timezone.timedelta(days=365),
                    razorpay_order_id=order_id,
                    razorpay_payment_id=payment_id,
                    razorpay_signature=signature,
                )

            bulk_order.status = 'paid'
            bulk_order.razorpay_payment_id = payment_id
            bulk_order.fulfilled_at = datetime.datetime.now()
            bulk_order.error = ''
            bulk_order.save()
    except ValueError as exc:
        # The company has paid: keep the order visible for a manual fix / refund.
        InsuranceBulkOrder.objects.filter(pk=bulk_order.pk).update(
            status='failed', razorpay_payment_id=payment_id, error=str(exc),
        )
        logger.error('Insurance bulk order %s paid by %s but NOT fulfilled (see insurance_bulk_orders.error)',
                     order_id, payment_id)
        raise InsurancePaymentRejected(str(exc))
    logger.info('Insurance bulk order %s fulfilled by payment %s', order_id, payment_id)
    return bulk_order, True

@login_required
def checkout_online_success(request):
    user = request.user
    if not (is_insurance_manager(user) or is_insurance_onboarding(user) or is_insurance_sales(user)):
        return JsonResponse({'success': False, 'message': 'Unauthorized.'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=405)

    cart = request.session.get('insurance_bulk_cart', [])
    if not cart:
        return JsonResponse({'success': False, 'message': 'Your cart is empty or already processed.'}, status=400)

    payment_ref = request.POST.get('razorpay_payment_id')
    order_id = request.POST.get('razorpay_order_id')
    signature = request.POST.get('razorpay_signature')

    key = getattr(settings, 'RAZORPAY_KEY', '')
    secret = getattr(settings, 'RAZORPAY_SECRET', '')
    is_mock_payment = not bool(key and secret and razorpay) and getattr(settings, 'DEBUG', False)

    if not is_mock_payment:
        if not (key and secret and razorpay):
            return JsonResponse({'success': False, 'message': USER_PAYMENT_UNAVAILABLE}, status=500)

        expected_order_id = request.session.get('insurance_bulk_order_id')
        if not expected_order_id or expected_order_id != order_id:
            return JsonResponse({'success': False, 'message': 'Invalid order ID.'}, status=400)

        client = razorpay.Client(auth=(key, secret))
        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_ref,
                'razorpay_signature': signature
            })
        except razorpay.errors.SignatureVerificationError:
            return JsonResponse({'success': False, 'message': 'Invalid payment signature.'}, status=400)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Failed to verify payment: {str(e)}'}, status=400)
    else:
        if not getattr(settings, 'DEBUG', False):
            return JsonResponse({'success': False, 'message': 'Mock payments are disabled in production.'}, status=403)
        order_id = order_id or 'order_local_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        if not payment_ref:
            payment_ref = 'TEST_PAY_' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

    try:
        # Mock checkouts, and carts whose order predates InsuranceBulkOrder, have
        # no row yet; the order id is this session's own (checked above).
        bulk_order, _created = InsuranceBulkOrder.objects.get_or_create(
            razorpay_order_id=order_id,
            defaults={
                'created_by': user,
                'company_id': get_or_sync_insurance_company_id(user),
                'cart': cart,
                'amount_paise': int(sum(item.get('amount', 0) for item in cart) * 100),
            },
        )
        mock_payment = None
        if is_mock_payment:
            mock_payment = {'id': payment_ref, 'order_id': order_id, 'amount': bulk_order.amount_paise, 'status': 'captured'}
        fulfil_insurance_bulk_order(order_id, payment_ref, payment=mock_payment, signature=signature)
    except InsurancePaymentRejected as exc:
        return JsonResponse({'success': False, 'message': str(exc)}, status=400)
    except Exception as e:
        logger.error(f'Online checkout failed: {e}')
        return JsonResponse({'success': False, 'message': str(e)}, status=500)

    request.session.pop('insurance_bulk_cart', None)
    request.session.pop('insurance_bulk_order_id', None)

    return JsonResponse({
        'success': True,
        'message': 'Online payment completed successfully. Agents onboarded!',
        'redirect': '/insurance/agents/',
        'redirect_url': '/insurance/agents/'
    })
