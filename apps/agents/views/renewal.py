"""Agent subscription renewal — lets an active (or expired) agent pay for
another year on their current plan without going back through registration."""
import logging
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
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
    mock_payment_id,
    MOCK_SIGNATURE,
)

logger = logging.getLogger(__name__)

_PLAN_DISPLAY = {
    'starter': PLAN_LABELS.get('starter', 'Starter'),
    'professional': PLAN_LABELS.get('professional', 'Professional'),
}


def _renewal_price_paise(plan_type, pricing_config):
    """Return renewal amount in paise (same as new-signup full price, incl. GST)."""
    cfg_key = 'starter' if plan_type == 'starter' else 'professional'
    defaults = {'starter': 1999, 'professional': 9999}
    base = float(pricing_config.get(cfg_key, {}).get('full_price', defaults[cfg_key]))
    total = round(base + (base * 0.18), 2)
    return int(total * 100)


@login_required(login_url='agents:agent_login')
@require_http_methods(['GET', 'POST'])
def renew_plan(request):
    from apps.agents.services.account_auth import resolve_agent_for_user, agent_can_access_dashboard
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
        cfg = pricing_config.get('starter' if plan_type == 'starter' else 'professional', {})
        base_price = float(cfg.get('full_price', 1999 if plan_type == 'starter' else 9999))
        gst = round(base_price * 0.18, 2)
        total = round(base_price + gst, 2)

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

    # One pending renewal at a time: cancel any existing pending renewal sub.
    AgentSubscription.objects.filter(
        agent=agent, payment_status='pending', status='inactive',
        selected_plan__endswith='(Renewal)',
    ).delete()

    sub = AgentSubscription.objects.create(
        agent=agent,
        selected_plan=plan_name_stored,
        registration_amount=amount_paise / 100,
        payment_status='pending',
        status='inactive',
    )

    mock_checkout = should_mock_razorpay(request)
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
