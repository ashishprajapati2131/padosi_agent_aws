"""Agent subscription renewal — lets an active (or expired) agent pay for
another year on their current plan without going back through registration."""
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from apps.agents.models import AgentSubscription
from apps.home.models import SiteSetting
from apps.agents.services.feature_unlock import (
    PLAN_LABELS,
    normalize_plan_slug,
    paid_plan_label,
)
from apps.agents.services.razorpay_checkout import (
    checkout_payload,
    create_checkout_order,
    should_mock_razorpay,
)

logger = logging.getLogger(__name__)

_PLAN_DISPLAY = {
    'starter': PLAN_LABELS.get('starter', 'Starter'),
    'professional': PLAN_LABELS.get('professional', 'Professional'),
}


def _renewal_price_paise(plan_type, pricing_config):
    """Return renewal amount in paise (same as new-signup full price, incl. GST)."""
    # Same whole-rupee GST bundle as the signup checkout. int(total * 100) truncated
    # (2358.82 -> 235881 paise) and differed from what the signup page charges (audit PAY13).
    from apps.agents.views.registration import _gst_bundle_from_base

    _base, _gst, total = _gst_bundle_from_base(_renewal_base(plan_type, pricing_config))
    return int(total) * 100


def _renewal_base(plan_type, pricing_config):
    cfg_key = 'starter' if plan_type == 'starter' else 'professional'
    defaults = {'starter': 1999, 'professional': 9999}
    return float(pricing_config.get(cfg_key, {}).get('full_price', defaults[cfg_key]))


@login_required(login_url='agents:agent_login')
@require_http_methods(['GET', 'POST'])
def renew_plan(request):
    from apps.agents.services.account_auth import resolve_agent_for_user
    try:
        agent = resolve_agent_for_user(request.user)
    except Exception:
        agent = None
    if not agent:
        return redirect('agents:agent_login')

    # Only active (or recently expired) paid agents can renew.
    plan_type = normalize_plan_slug(agent.plan_type or '')
    if plan_type not in ('starter', 'professional'):
        return redirect('agents:agent_dashboard')

    pricing_config = SiteSetting.get_value('pricing_config') or {}

    active_sub = (
        AgentSubscription.objects
        .filter(agent=agent, payment_status='completed', status='active')
        .order_by('-expires_at')
        .first()
    )

    if request.method == 'GET':
        amount_paise = _renewal_price_paise(plan_type, pricing_config)
        from apps.agents.views.registration import _gst_bundle_from_base

        base_price, gst, total = _gst_bundle_from_base(_renewal_base(plan_type, pricing_config))

        new_expiry = None
        if active_sub and active_sub.expires_at:
            now_dt = datetime.now()
            exp = active_sub.expires_at.replace(tzinfo=None) if hasattr(active_sub.expires_at, 'tzinfo') and active_sub.expires_at.tzinfo else active_sub.expires_at
            base_expiry = exp if exp > now_dt else now_dt
            new_expiry = base_expiry + timedelta(days=365)

        return render(request, 'agents/renew_plan.html', {
            'agent': agent,
            'plan_name': _PLAN_DISPLAY.get(plan_type, paid_plan_label(plan_type)),
            'plan_type': plan_type,
            'base_price': base_price,
            'gst': gst,
            'total': total,
            'amount_paise': amount_paise,
            'active_sub': active_sub,
            'new_expiry': new_expiry,
        })

    # POST — create order and return checkout payload
    amount_paise = _renewal_price_paise(plan_type, pricing_config)
    plan_name = _PLAN_DISPLAY.get(plan_type, paid_plan_label(plan_type))
    plan_name_stored = f'{plan_name} (Renewal)'

    # Drop only abandoned rows that never got a Razorpay order. A row with an order id must stay:
    # a late UPI payment on it is found by that id, deleting it lost the money (audit PAY4).
    AgentSubscription.objects.filter(
        agent=agent, payment_status='pending', status='inactive',
        selected_plan__endswith='(Renewal)',
    ).filter(Q(razorpay_order_id__isnull=True) | Q(razorpay_order_id='')).delete()

    sub = AgentSubscription.objects.create(
        agent=agent,
        selected_plan=plan_name_stored,
        registration_amount=amount_paise / 100,
        payment_status='pending',
        status='inactive',
    )

    # Automated tests must not call the live Razorpay API (CI often has test keys only).
    mock_checkout = should_mock_razorpay(request) or getattr(settings, 'TESTING', False)
    if mock_checkout:
        from apps.agents.services.razorpay_checkout import MOCK_ORDER_PREFIX
        import uuid
        razorpay_order_id = f'{MOCK_ORDER_PREFIX}{uuid.uuid4().hex[:12]}'
    else:
        razorpay_order_id, _ = create_checkout_order(
            amount_paise,
            receipt=f'renew-{agent.id}-{sub.pk}',
            request=request,
            notes={'agent_id': str(agent.id), 'type': 'renewal'},
        )
        if not razorpay_order_id:
            sub.delete()
            return JsonResponse({'success': False, 'message': 'Payment gateway error. Please try again.'}, status=502)

    sub.razorpay_order_id = razorpay_order_id
    sub.save(update_fields=['razorpay_order_id'])

    request.session['pending_checkout'] = {
        'agent_id': agent.id,
        'order_id': razorpay_order_id,
        'plan_type': plan_type,
        'plan_name': plan_name_stored,
    }
    request.session.modified = True

    return JsonResponse(checkout_payload(
        razorpay_order_id,
        amount_paise,
        agent,
        is_mock=mock_checkout,
        request=request,
    ))
