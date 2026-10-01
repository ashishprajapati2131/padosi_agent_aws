import json
import logging
import os
import re
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.conf import settings

from apps.agents.models import Agent, AgentDraft, AgentSubscription, Invoice
from apps.agents.services.razorpay_checkout import razorpay_client, _dotenv_file_maps, razorpay_credentials
from padosi_agent.razorpay_env import credential_pair_from_mapping
from apps.agents.services.post_payment import fulfill_invoice_and_welcome
from apps.agents.views.registration import (
    create_agent_from_draft,
    create_or_link_django_user,
    verify_and_activate_pending_payment,
)
from .dashboard import _get_admin_from_session

logger = logging.getLogger(__name__)


def _get_razorpay_clients():
    """
    Returns list of available (mode, client) pairs.
    Checks razorpay_client() first (supports test mocks), then checks other mappings in dotenv / env / settings.
    If none found, returns empty list.
    """
    import razorpay

    clients = []
    seen = set()

    # 1. Primary configured client (honors test mocks and standard settings)
    primary = razorpay_client()
    if primary:
        clients.append(('primary', primary))

    # 2. Check all sources from .env, os.environ, or settings for alternate keys
    sources = list(_dotenv_file_maps())
    sources.append(os.environ)
    sources.append({
        'RAZORPAY_KEY': getattr(settings, 'RAZORPAY_KEY', ''),
        'RAZORPAY_SECRET': getattr(settings, 'RAZORPAY_SECRET', ''),
        'RAZORPAY_KEY_ID': getattr(settings, 'RAZORPAY_KEY_ID', ''),
        'RAZORPAY_KEY_SECRET': getattr(settings, 'RAZORPAY_KEY_SECRET', ''),
    })

    # Allow optional secondary/fallback live keys via environment variables (never hardcoded)
    fallback_key = os.environ.get('RAZORPAY_LIVE_KEY') or os.environ.get('RAZORPAY_FALLBACK_KEY', '')
    fallback_secret = os.environ.get('RAZORPAY_LIVE_SECRET') or os.environ.get('RAZORPAY_FALLBACK_SECRET', '')
    if fallback_key and fallback_secret:
        sources.append({
            'RAZORPAY_KEY': fallback_key.strip(),
            'RAZORPAY_SECRET': fallback_secret.strip(),
        })

    for src in sources:
        k, s = credential_pair_from_mapping(src)
        if k and s and k not in seen:
            seen.add(k)
            mode = 'live' if k.startswith('rzp_live_') else 'test'
            try:
                clients.append((mode, razorpay.Client(auth=(k, s))))
            except Exception:
                pass

    return clients


def _plan_details_from_amount(amount_rupees: float, notes: dict = None) -> tuple[str, str]:
    """
    Infer plan slug and plan name from paid amount or Razorpay order notes.
    """
    if notes and isinstance(notes, dict):
        if notes.get('plan_type'):
            slug = str(notes.get('plan_type')).strip().lower()
            name = str(notes.get('plan_name') or slug.title())
            return slug, name

    amt = round(float(amount_rupees or 0), 2)
    if amt <= 1.00:
        return 'free_trial', 'Trial Plan'
    if 2000 <= amt <= 3000:
        return 'starter', "Starter's Plan"
    if 5000 <= amt <= 9000:
        return 'professional', "Professional's Plan"
    if amt > 9000:
        return 'exclusive', "Exclusive Plan"

    return 'professional', "Professional's Plan"


def _is_admin_authenticated(request):
    """
    Authenticate admin session via:
    1. Custom session_token cookie (user_sessions DB table)
    2. Django auth user (is_staff or is_superuser)
    3. Session dict ('admin_user' or 'admin_id')
    Returns integer admin ID or dict, or None.
    """
    try:
        admin_id = _get_admin_from_session(request)
        if admin_id:
            return admin_id
    except Exception as e:
        logger.warning(f"Error checking admin session token: {e}")

    if hasattr(request, 'user') and request.user and request.user.is_authenticated:
        if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False):
            return getattr(request.user, 'id', 1) or 1

    if hasattr(request, 'session'):
        admin_user = request.session.get('admin_user')
        if admin_user and isinstance(admin_user, dict):
            return admin_user.get('id', 1)
        if request.session.get('admin_id'):
            return request.session.get('admin_id')

    return None


@require_http_methods(["GET"])
def payment_reconcile_dashboard(request):
    """
    Admin dashboard for payment reconciliation, recovery, and manual verification.
    Strictly restricted to authenticated admins.
    """
    admin = _is_admin_authenticated(request)
    if not admin:
        return redirect("admin_login_page")

    # 1. Agents with pending or failed payment subscriptions
    pending_agents = Agent.objects.filter(
        subscriptions__payment_status__in=['pending', 'failed']
    ).distinct().order_by('-created_at')[:30]

    # 2. Agent drafts with registration step >= 1 where an Agent record was not yet created
    existing_agent_emails = Agent.objects.values_list('email', flat=True)
    pending_drafts = AgentDraft.objects.filter(
        registration_step__gte=1
    ).exclude(
        email__in=existing_agent_emails
    ).order_by('-created_at')[:30]

    # 3. Overall Reconciliation KPIs
    total_invoices_paid = Invoice.objects.filter(payment_status='paid').count()
    total_pending_subs = AgentSubscription.objects.filter(payment_status__in=['pending', 'failed']).count()
    total_orphan_drafts = pending_drafts.count()

    context = {
        'admin': admin,
        'pending_agents': pending_agents,
        'pending_drafts': pending_drafts,
        'stats': {
            'total_invoices_paid': total_invoices_paid,
            'total_pending_subs': total_pending_subs,
            'total_orphan_drafts': total_orphan_drafts,
        }
    }
    return render(request, "admin/payments/reconcile.html", context)


@require_http_methods(["POST"])
def reconcile_inspect_payment(request):
    """
    Secure AJAX endpoint to inspect a Razorpay Payment ID, Order ID, or Agent Email.
    Queries Razorpay live and matches with database records (Agent, Draft, Invoice).
    Always returns HTTP 200 JSON to ensure client error messages are visible.
    """
    try:
        admin = _is_admin_authenticated(request)
        if not admin:
            return JsonResponse({'success': False, 'message': 'Unauthorized admin session'}, status=403)

        try:
            body = json.loads(request.body) if request.body else request.POST
            raw_query = str(body.get('query', '')).strip()
        except Exception:
            raw_query = str(request.POST.get('query', '')).strip()

        if not raw_query:
            return JsonResponse({'success': False, 'message': 'Please provide a Payment ID, Order ID, or Email.'})

        clients = _get_razorpay_clients()
        if not clients:
            return JsonResponse({
                'success': False,
                'message': 'Razorpay client is not configured. Please check RAZORPAY_KEY and RAZORPAY_SECRET in environment.'
            })

        # Robust regex extraction to handle messy user inputs like 'Order_id:-order_TgAtfYxCS12pG6'
        pay_m = re.search(r'(pay_[a-zA-Z0-9]{8,})', raw_query, re.IGNORECASE)
        ord_m = re.search(r'(order_[a-zA-Z0-9]{8,})', raw_query, re.IGNORECASE)
        email_m = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', raw_query)

        query_pay_id = pay_m.group(1) if pay_m else ''
        query_order_id = ord_m.group(1) if ord_m else ''
        query_email = email_m.group(1).lower() if email_m else ''

        payment_data = None
        order_data = None
        order_id = query_order_id
        payment_id = query_pay_id
        last_err = None

        # Priority 1: Direct Payment ID
        if query_pay_id:
            for mode, cl in clients:
                try:
                    payment_data = cl.payment.fetch(query_pay_id)
                    payment_id = query_pay_id
                    order_id = payment_data.get('order_id') or order_id
                    break
                except Exception as e:
                    last_err = e

        # Priority 2: Order ID
        if not payment_data and query_order_id:
            for mode, cl in clients:
                try:
                    ord_info = cl.order.fetch(query_order_id)
                    pmts = cl.order.payments(query_order_id)
                    order_data = ord_info
                    order_id = query_order_id
                    items = pmts.get('items', []) if pmts else []
                    if items:
                        successful = [p for p in items if p.get('status') in ('captured', 'authorized')]
                        payment_data = successful[0] if successful else items[0]
                        payment_id = payment_data.get('id') or ''
                    else:
                        payment_data = {
                            'id': f'pay_for_{query_order_id}',
                            'order_id': query_order_id,
                            'amount': ord_info.get('amount', 0),
                            'status': 'captured' if ord_info.get('status') == 'paid' else ord_info.get('status', 'created'),
                            'email': '',
                            'contact': '',
                            'notes': ord_info.get('notes') or {},
                            'method': 'online',
                        }
                    break
                except Exception as e:
                    last_err = e

        # Priority 3: Email lookup
        if not payment_data and query_email:
            email = query_email
            agent = None
            sub = None
            draft = None
            try:
                agent = Agent.objects.filter(email__iexact=email).first()
                if agent:
                    sub = AgentSubscription.objects.filter(agent=agent).order_by('-created_at').first()
                draft = AgentDraft.objects.filter(email__iexact=email).first()
            except Exception as e:
                logger.warning(f"Error querying Agent/Draft by email: {e}")

            target_order_id = (sub.razorpay_order_id if sub and sub.razorpay_order_id else '')
            if not target_order_id and draft and hasattr(draft, 'registration_draft') and isinstance(draft.registration_draft, dict):
                target_order_id = draft.registration_draft.get('razorpay_order_id', '') or draft.registration_draft.get('order_id', '')

            if target_order_id and target_order_id.startswith('order_'):
                order_id = target_order_id
                for mode, cl in clients:
                    try:
                        ord_info = cl.order.fetch(target_order_id)
                        pmts = cl.order.payments(target_order_id)
                        order_data = ord_info
                        items = pmts.get('items', []) if pmts else []
                        if items:
                            successful = [p for p in items if p.get('status') in ('captured', 'authorized')]
                            payment_data = successful[0] if successful else items[0]
                            payment_id = payment_data.get('id') or ''
                        break
                    except Exception as e:
                        last_err = e

            if not payment_data:
                db_agent_data = None
                db_draft_data = None
                try:
                    if agent:
                        db_agent_data = {
                            'id': agent.id,
                            'name': getattr(agent, 'fullname', '') or getattr(agent, 'name', ''),
                            'email': agent.email,
                            'mobile': agent.mobile,
                            'status': agent.status,
                            'has_paid_invoice': Invoice.objects.filter(agent_email__iexact=email, payment_status='paid').exists()
                        }
                    if draft:
                        db_draft_data = {
                            'id': draft.id,
                            'name': getattr(draft, 'fullname', '') or getattr(draft, 'name', ''),
                            'email': draft.email,
                            'mobile': draft.mobile,
                            'step': getattr(draft, 'registration_step', 1)
                        }
                except Exception as e:
                    logger.warning(f"Error fetching DB match: {e}")

                return JsonResponse({
                    'success': True,
                    'has_razorpay': False,
                    'message': f'Found database records for {query_email}, but no completed Razorpay order was attached. Please search by Order ID or Payment ID to link.',
                    'agent': db_agent_data,
                    'draft': db_draft_data,
                })

        if not payment_data:
            err_msg = f'No payment or order found on Razorpay for query "{raw_query}".'
            if last_err:
                err_msg += f' (Razorpay returned: {last_err})'
            return JsonResponse({'success': False, 'message': err_msg})

        # Format Razorpay payload
        amt_paise = payment_data.get('amount', 0)
        amt_rupees = round(amt_paise / 100.0, 2)
        cust_email = str(payment_data.get('email') or query_email or '').strip().lower()
        cust_contact = str(payment_data.get('contact') or '').strip()
        status = payment_data.get('status', 'unknown')
        notes = payment_data.get('notes')
        if not isinstance(notes, dict):
            notes = {}
        method = payment_data.get('method', 'N/A')

        inferred_slug, inferred_name = _plan_details_from_amount(amt_rupees, notes)

        # Match receipt draft if available (e.g. 'agent_draft_99_1790318572')
        receipt = (order_data.get('receipt') if order_data else '') or (payment_data.get('receipt') if payment_data else '')
        matched_draft = None
        matched_agent = None
        existing_invoice = None

        try:
            if cust_email:
                matched_draft = AgentDraft.objects.filter(email__iexact=cust_email).first()
            if not matched_draft and receipt and 'draft_' in receipt:
                m = re.search(r'draft_(\d+)', receipt)
                if m:
                    matched_draft = AgentDraft.objects.filter(pk=int(m.group(1))).first()

            if matched_draft:
                if not cust_email:
                    cust_email = (getattr(matched_draft, 'email', '') or '').strip().lower()
                if not cust_contact:
                    cust_contact = getattr(matched_draft, 'mobile', '') or ''

            # Match in Database
            if cust_email:
                matched_agent = Agent.objects.filter(email__iexact=cust_email).first()
            if not matched_agent and order_id:
                sub_match = AgentSubscription.objects.filter(razorpay_order_id=order_id).first()
                if sub_match and getattr(sub_match, 'agent_id', None):
                    try:
                        matched_agent = Agent.objects.filter(id=sub_match.agent_id).first()
                    except Exception:
                        matched_agent = None

            if payment_id and not payment_id.startswith('pay_for_'):
                existing_invoice = Invoice.objects.filter(razorpay_payment_id=payment_id).first()
            if not existing_invoice and order_id:
                existing_invoice = Invoice.objects.filter(razorpay_order_id=order_id).first()
            if not matched_agent and existing_invoice and getattr(existing_invoice, 'agent_id', None):
                try:
                    matched_agent = Agent.objects.filter(id=existing_invoice.agent_id).first()
                except Exception:
                    pass
        except Exception as db_e:
            logger.warning(f"Error querying local DB for matched records: {db_e}")

        return JsonResponse({
            'success': True,
            'has_razorpay': True,
            'razorpay': {
                'payment_id': payment_id,
                'order_id': order_id,
                'receipt': receipt,
                'amount_rupees': amt_rupees,
                'amount_paise': amt_paise,
                'status': status,
                'is_captured': status in ('captured', 'authorized'),
                'email': cust_email,
                'contact': cust_contact,
                'method': method,
                'notes': notes,
                'inferred_plan_type': inferred_slug,
                'inferred_plan_name': inferred_name,
            },
            'db_match': {
                'agent': {
                    'id': matched_agent.id,
                    'name': getattr(matched_agent, 'fullname', '') or getattr(matched_agent, 'name', ''),
                    'email': getattr(matched_agent, 'email', ''),
                    'mobile': getattr(matched_agent, 'mobile', ''),
                    'status': getattr(matched_agent, 'status', ''),
                } if matched_agent else None,
                'draft': {
                    'id': matched_draft.id,
                    'name': getattr(matched_draft, 'fullname', '') or getattr(matched_draft, 'name', ''),
                    'email': getattr(matched_draft, 'email', ''),
                    'mobile': getattr(matched_draft, 'mobile', ''),
                    'step': getattr(matched_draft, 'registration_step', 1),
                } if matched_draft else None,
                'invoice': {
                    'id': existing_invoice.id,
                    'invoice_number': getattr(existing_invoice, 'invoice_number', ''),
                    'amount': float(getattr(existing_invoice, 'total_amount', 0) or 0),
                    'synced_to_sheet': getattr(existing_invoice, 'synced_to_sheet', False),
                } if existing_invoice else None,
            }
        })

    except Exception as e:
        logger.exception(f"[reconcile_inspect_payment ERROR]: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Server Error during inspect: {str(e)}'
        })


_PAY_ID_RE = re.compile(r'^pay_[A-Za-z0-9]{8,30}$')
_ORDER_ID_RE = re.compile(r'^order_[A-Za-z0-9]{8,30}$')
_KNOWN_PLANS = ('free_trial', 'starter', 'professional', 'exclusive')
_RECONCILE_PLAN_NAMES = {
    'free_trial': 'Trial Plan',
    'starter': "Starter's Plan",
    'professional': "Professional's Plan",
    'exclusive': 'Exclusive Plan',
}


def _reconcile_clients():
    """Razorpay clients allowed to prove a payment.

    Outside DEBUG only live keys count: production can still hold test keys in
    .env, and a test-mode "captured" payment involves no real money.
    """
    from apps.agents.services.razorpay_checkout import razorpay_key_mode
    clients = _get_razorpay_clients()
    if settings.DEBUG:
        return clients
    primary_live = razorpay_key_mode() == 'live'
    return [(mode, cl) for mode, cl in clients if mode == 'live' or (mode == 'primary' and primary_live)]


def _fetch_captured_payment(clients, payment_id, order_id):
    """Return (payment, order_id, receipt, error). Only a captured payment counts."""
    payment = None
    receipt = ''
    if payment_id:
        for _mode, cl in clients:
            try:
                payment = cl.payment.fetch(payment_id)
                order_id = payment.get('order_id') or order_id
                break
            except Exception:
                continue
    if order_id:
        for _mode, cl in clients:
            try:
                receipt = (cl.order.fetch(order_id) or {}).get('receipt', '') or ''
                if not payment:
                    items = (cl.order.payments(order_id) or {}).get('items', [])
                    captured = [p for p in items if p.get('status') == 'captured']
                    payment = captured[0] if captured else (items[0] if items else None)
                break
            except Exception:
                continue
    if not payment:
        return None, order_id, receipt, 'No payment was found on Razorpay for this Payment ID / Order ID.'
    if payment.get('status') != 'captured':
        return None, order_id, receipt, (
            f"Razorpay shows this payment as '{payment.get('status')}', not captured. "
            "Only captured payments can be reconciled (capture it in the Razorpay dashboard first)."
        )
    if order_id and payment.get('order_id') and payment.get('order_id') != order_id:
        return None, order_id, receipt, 'This payment belongs to a different Razorpay order.'
    return payment, payment.get('order_id') or order_id, receipt, None


def _reconcile_subscription(order_id, receipt, email, payment, plan_type):
    """Find the subscription this paid order belongs to (or create its row).

    The order's own subscription always wins. A paid order with no row (lost
    by an old checkout bug) is rebuilt from its notes. Only then is a draft /
    agent matched by email, and a new row is created for this order, never by
    re-pointing another subscription. No agent is invented from payer data.
    Returns (agent, subscription, error).
    """
    from apps.agents.views.registration import adopt_orphan_registration_order

    sub = AgentSubscription.objects.filter(razorpay_order_id=order_id).first() if order_id else None
    if not sub and order_id:
        sub = adopt_orphan_registration_order(order_id)
    if sub:
        return sub.agent, sub, None

    draft = None
    m = re.search(r'draft_(\d+)', receipt or '')
    if m:
        draft = AgentDraft.objects.filter(pk=int(m.group(1))).first()
    agent = Agent.objects.filter(email__iexact=draft.email).first() if draft else None
    if not agent and email:
        agent = Agent.objects.filter(email__iexact=email).first()
    if not agent and not draft and email:
        draft = AgentDraft.objects.filter(email__iexact=email).first()
    if not agent and not draft:
        return None, None, (
            'No registered agent or registration draft matches this payment. '
            'Search by the email the agent registered with.'
        )

    notes = payment.get('notes') if isinstance(payment.get('notes'), dict) else {}
    paid_rupees = Decimal(int(payment.get('amount') or 0)) / 100
    slug = str(notes.get('plan_type') or '').strip().lower()
    if slug not in _KNOWN_PLANS:
        slug = plan_type if plan_type in _KNOWN_PLANS else _plan_details_from_amount(float(paid_rupees))[0]
    plan_name = _RECONCILE_PLAN_NAMES[slug]
    if not agent:
        agent = create_agent_from_draft(draft, plan_type=slug, plan_name=plan_name, status='pending_payment')
    sub = AgentSubscription.objects.create(
        agent=agent, selected_plan=plan_name, registration_amount=paid_rupees,
        payment_status='pending', status='inactive', razorpay_order_id=order_id or None,
    )
    return agent, sub, None


def _already_done(agent, subscription):
    return JsonResponse({
        'success': True,
        'message': f'Already reconciled: {agent.fullname} has this payment on subscription #{subscription.pk}.',
        'agent_id': agent.id, 'agent_name': agent.fullname,
        'invoice_number': '', 'synced_to_sheet': False,
    })


@require_http_methods(["POST"])
def reconcile_execute_payment(request):
    """
    Activate the agent for a captured Razorpay payment that the normal flow missed.

    Same activation as checkout recovery (_activate_paid_subscription: locked,
    idempotent, plan from the order, referral credit, superseded rows); the
    invoice + welcome email are then sent once, outside the transaction.
    """
    try:
        admin = _is_admin_authenticated(request)
        if not admin:
            return JsonResponse({'success': False, 'message': 'Unauthorized admin session'}, status=403)
        admin_id_val = admin.get('id', 1) if isinstance(admin, dict) else admin

        try:
            body = json.loads(request.body) if request.body else request.POST
            payment_id = str(body.get('payment_id', '')).strip()
            order_id = str(body.get('order_id', '')).strip()
            email = str(body.get('email', '')).strip().lower()
            plan_type = str(body.get('plan_type', '')).strip().lower()
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid request data.'})

        if payment_id.startswith('pay_for_'):
            payment_id = ''  # placeholder Inspect shows for an order without payments
        if payment_id and not _PAY_ID_RE.match(payment_id):
            return JsonResponse({'success': False, 'message': 'Invalid Payment ID format.'})
        if order_id and not _ORDER_ID_RE.match(order_id):
            return JsonResponse({'success': False, 'message': 'Invalid Order ID format.'})
        if not payment_id and not order_id:
            return JsonResponse({'success': False, 'message': 'A Razorpay Payment ID or Order ID is required.'})

        clients = _reconcile_clients()
        if not clients:
            return JsonResponse({'success': False, 'message': 'Live Razorpay keys are not configured.'})

        payment, order_id, receipt, error = _fetch_captured_payment(clients, payment_id, order_id)
        if error:
            return JsonResponse({'success': False, 'message': error})
        payment_id = payment.get('id') or payment_id
        payer_email = str(payment.get('email') or '').strip().lower()

        used = AgentSubscription.objects.filter(razorpay_payment_id=payment_id, payment_status='completed').first()
        if used and (used.razorpay_order_id or '') != (order_id or ''):
            return JsonResponse({
                'success': False,
                'message': f'Payment {payment_id} is already attached to another subscription '
                           f'(#{used.pk}, agent #{used.agent_id}).',
            })

        from apps.agents.views.registration import (
            _activate_paid_subscription,
            _expected_amount_paise,
            _paise_amounts_match,
        )
        agent, subscription, error = _reconcile_subscription(order_id, receipt, email or payer_email, payment, plan_type)
        if error:
            return JsonResponse({'success': False, 'message': error})

        if subscription.payment_status == 'completed':
            if (subscription.razorpay_payment_id or '') == payment_id:
                return _already_done(agent, subscription)
            return JsonResponse({'success': False, 'message': 'This order is already completed with a different payment.'})

        paid_paise = int(payment.get('amount') or 0)
        if not _paise_amounts_match(paid_paise, _expected_amount_paise(subscription.registration_amount)):
            return JsonResponse({
                'success': False,
                'message': (f'Amount mismatch: Razorpay received Rs {paid_paise / 100:.2f}, '
                            f'the order expects Rs {subscription.registration_amount}. Not activated.'),
            })

        subscription, activated = _activate_paid_subscription(
            agent, subscription, payment, log_label='[Reconciliation]', queue_fulfilment=False,
        )
        agent.refresh_from_db()
        if not activated:
            return _already_done(agent, subscription)

        try:
            with transaction.atomic():
                from apps.admin_panel.models import AdminActivityLog
                AdminActivityLog.log(
                    'Reconciled Razorpay payment', 'AgentSubscription', subscription.pk,
                    details=f'payment={payment_id} order={order_id} agent={agent.pk}', request=request,
                )
        except Exception as log_err:
            logger.warning('[Reconciliation] Activity log failed: %s', log_err)
        logger.info('[Reconciliation] Admin #%s activated agent #%s with %s / %s',
                    admin_id_val, agent.pk, payment_id, order_id)

        # Invoice, Drive/Sheets sync and welcome email: once, after commit.
        invoice = None
        try:
            invoice = fulfill_invoice_and_welcome(agent, subscription)
        except Exception as ful_err:
            logger.exception('[Reconciliation] Fulfilment failed for agent #%s: %s', agent.pk, ful_err)

        if invoice:
            tail = f", Invoice #{invoice.invoice_number} generated."
        else:
            tail = ". The invoice could not be generated; create it from Invoices."
        return JsonResponse({
            'success': True,
            'message': f"Payment reconciled! {agent.fullname} is activated (status: {agent.status})" + tail,
            'agent_id': agent.id,
            'agent_name': agent.fullname,
            'invoice_number': getattr(invoice, 'invoice_number', '') if invoice else '',
            'synced_to_sheet': bool(getattr(invoice, 'synced_to_sheet', False)) if invoice else False,
        })

    except Exception as e:
        logger.exception(f"[Reconciliation Global Error]: {e}")
        return JsonResponse({'success': False, 'message': 'Reconciliation failed. See the server log for details.'})
