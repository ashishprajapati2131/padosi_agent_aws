from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.agents.models import Agent, AgentSubscription
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.conf import settings
from django.db import transaction
import logging
import random, string, datetime

# Optional razorpay import
try:
    import razorpay
except ImportError:
    razorpay = None

from apps.insurance.decorators import insurance_manager_or_accounts_required
from padosi_agent.razorpay_env import USER_PAYMENT_UNAVAILABLE

logger = logging.getLogger(__name__)


@login_required
@insurance_manager_or_accounts_required
def payments_index(request):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agents = (
        Agent.objects.filter(insurance_id=company_id, status="pending_accounts_payment")
        .prefetch_related("subscriptions")
        .order_by("-created_at")
    )

    return render(request, "insurance/payments/index.html", {"agents": agents})


@login_required
@insurance_manager_or_accounts_required
def record_payment(request, agent_id):
    """Records an offline payment (NEFT/Cheque/UPI/Cash) against an agent's
    pending subscription, mirroring Laravel's offline checkoutCart flow:
    agent -> pending_admin_approval + payment audit fields; subscription completed."""

    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Invalid request method."}, status=405
        )

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    payment_method = request.POST.get("payment_method", "").strip()
    payment_reference = request.POST.get("payment_reference", "").strip()
    payment_recorded_at = request.POST.get("payment_recorded_at", "").strip()

    errors = []
    if not payment_method:
        errors.append("Payment method is required.")
    if not payment_reference:
        errors.append("Transaction reference / UTR is required.")
    elif payment_reference.lower().startswith(("order_", "pay_")):
        # The reference is stored with the subscription, and a Razorpay-looking
        # id there unlocked the agent dashboard as if paid online.
        errors.append(
            "Enter the bank / UPI / cheque reference here, not a Razorpay id."
        )
    if not payment_recorded_at:
        errors.append("Payment date is required.")

    recorded_dt = None
    if payment_recorded_at:
        recorded_dt = parse_date(payment_recorded_at)
        if not recorded_dt:
            errors.append("Payment date is invalid.")
        elif recorded_dt > datetime.date.today():
            # The date starts the 365-day subscription.
            errors.append("Payment date cannot be in the future.")

    if errors:
        msg = " ".join(errors)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("insurance:payments_index")

    recorded_at = datetime.datetime.combine(recorded_dt, datetime.datetime.min.time())

    try:
        with transaction.atomic():
            agent = Agent.objects.select_for_update().get(id=agent.id)
            if agent.status in ["pending_admin_approval", "active"]:
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Payment for this agent is already recorded.",
                        }
                    )
                messages.info(request, "Payment for this agent is already recorded.")
                return redirect("insurance:payments_index")

            agent.status = "pending_admin_approval"
            agent.payment_method = payment_method
            agent.payment_reference = payment_reference
            agent.payment_recorded_at = recorded_at
            agent.payment_recorded_by = request.user
            agent.save()

            subscription = (
                agent.subscriptions.filter(payment_status="pending")
                .order_by("-created_at")
                .select_for_update()
                .first()
            )
            if subscription:
                subscription.payment_status = "completed"
                # Keep the manual order id (INSURANCE_MANUAL_... set in agents_store); the UTR
                # lives on agent.payment_reference. Writing a Razorpay-looking id here breaks
                # invariant 9 and confuses the recovery/reconcile paths (audit INS3).
                subscription.starts_at = recorded_at
                subscription.expires_at = recorded_at + timezone.timedelta(days=365)
                subscription.save()

        success_msg = "Offline payment recorded. Agent advanced to admin approval."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": success_msg})
        messages.success(request, success_msg)
        return redirect("insurance:payments_index")

    except Exception as e:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {"success": False, "message": f"Failed to record payment: {str(e)}"},
                status=500,
            )
        messages.error(request, f"Failed to record payment: {str(e)}")
        return redirect("insurance:payments_index")


@login_required
@insurance_manager_or_accounts_required
def create_razorpay_order(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    subscription = (
        agent.subscriptions.filter(payment_status="pending")
        .order_by("-created_at")
        .first()
    )
    amount = (
        subscription.registration_amount
        if subscription
        else (2359 if agent.plan_type == "starter" else 8258)
    )

    key = getattr(settings, "RAZORPAY_KEY", "")
    secret = getattr(settings, "RAZORPAY_SECRET", "")
    is_test_key = key.startswith("rzp_test")

    order_id = None
    if key and secret and razorpay:
        client = razorpay.Client(auth=(key, secret))
        order_data = {
            "amount": int(amount * 100),
            "currency": "INR",
            "receipt": f"agent_ins_{agent.id}_{int(timezone.now().timestamp())}",
            "payment_capture": 1,
            "notes": {
                "agent_id": agent.id,
                "insurance_user_id": request.user.id,
            },
        }
        try:
            razorpay_order = client.order.create(data=order_data)
            order_id = razorpay_order["id"]
        except Exception as e:
            logger.error("Insurance Razorpay order failed: %s", e)
            return JsonResponse(
                {"success": False, "message": USER_PAYMENT_UNAVAILABLE}, status=500
            )
    elif not is_test_key and key:
        return JsonResponse(
            {"success": False, "message": USER_PAYMENT_UNAVAILABLE}, status=500
        )

    return JsonResponse(
        {
            "success": True,
            "order_id": order_id,
            "amount": int(amount * 100),
            "key": key,
            "name": request.user.first_name,
            "email": request.user.email,
            "test_payment": is_test_key or not key,
        }
    )


# Agent states that mean this agent's registration payment is already recorded.
INSURANCE_PAID_STATUSES = ("pending_admin_approval", "active")


class InsurancePaymentRejected(Exception):
    """This payment must not fulfil the order; retrying cannot change that."""


def _insurance_razorpay_client():
    # Same credentials create_razorpay_order / checkout_online_start use.
    key = getattr(settings, "RAZORPAY_KEY", "")
    secret = getattr(settings, "RAZORPAY_SECRET", "")
    return razorpay.Client(auth=(key, secret)) if key and secret and razorpay else None


def captured_insurance_payment(client, order_id, payment_id, payment=None):
    """Return the captured Razorpay payment of this order (invariant 10).

    ``payment`` is the payment entity when the caller already has it (webhook /
    recovery); otherwise it is fetched. Raises InsurancePaymentRejected.
    """
    from apps.agents.services.razorpay_checkout import ensure_payment_captured

    if not payment_id:
        raise InsurancePaymentRejected("Payment details missing.")
    try:
        if payment is None:
            if client is None:
                logger.error("Insurance payment - Razorpay keys not configured.")
                raise InsurancePaymentRejected(USER_PAYMENT_UNAVAILABLE)
            payment = client.payment.fetch(payment_id)
        payment = ensure_payment_captured(client, payment)
    except InsurancePaymentRejected:
        raise
    except Exception as exc:
        logger.error(
            "Insurance payment - verification failed for order %s: %s", order_id, exc
        )
        raise InsurancePaymentRejected(
            "Failed to verify payment. Please contact support."
        )
    if not payment or payment.get("id") != payment_id:
        logger.error(
            "Insurance payment %s for order %s is not captured", payment_id, order_id
        )
        raise InsurancePaymentRejected("Payment is not completed.")
    if payment.get("order_id") != order_id:
        logger.critical(
            "Insurance payment %s belongs to order %s, not %s",
            payment_id,
            payment.get("order_id"),
            order_id,
        )
        raise InsurancePaymentRejected("Payment does not belong to this order.")
    return payment


def _complete_insurance_agent_payment(agent_id, payment_ref, recorded_by):
    """Advance the agent to admin approval and complete its pending subscription.

    Returns False when the payment was already recorded (no second update).
    """
    with transaction.atomic():
        # Refresh from DB with lock
        agent = Agent.objects.select_for_update().get(id=agent_id)
        if agent.status in INSURANCE_PAID_STATUSES:
            return False

        agent.status = "pending_admin_approval"
        agent.payment_method = "Razorpay (Online)"
        agent.payment_reference = payment_ref
        agent.payment_recorded_at = timezone.now()
        agent.payment_recorded_by = recorded_by
        agent.save()

        subscription = (
            agent.subscriptions.filter(payment_status="pending")
            .order_by("-created_at")
            .select_for_update()
            .first()
        )
        if subscription:
            subscription.payment_status = "completed"
            subscription.razorpay_payment_id = payment_ref
            subscription.starts_at = timezone.now()
            subscription.expires_at = timezone.now() + timezone.timedelta(days=365)
            subscription.save()
    return True


def fulfil_insurance_agent_order(
    order_id, payment_id, payment=None, agent_id=None, order=None
):
    """Record a captured single-agent (``agent_ins_``) order exactly once.

    Shared by the browser callback, the Razorpay webhook and
    recover_orphaned_payments. The agent comes from the order's own notes
    (written by create_razorpay_order), never from the client; ``agent_id``
    (browser) must match them; ``order`` is the Razorpay order when the caller
    already fetched it. Returns (agent, fulfilled): fulfilled is False
    when the payment was already recorded. Raises InsurancePaymentRejected.
    """
    from django.contrib.auth.models import User
    from apps.agents.views.registration import (
        _expected_amount_paise,
        _paise_amounts_match,
    )

    client = _insurance_razorpay_client()
    if order is None:
        if client is None:
            logger.error("Insurance payment - Razorpay keys not configured.")
            raise InsurancePaymentRejected(USER_PAYMENT_UNAVAILABLE)
        order = client.order.fetch(
            order_id
        )  # network errors propagate: the webhook retries
    notes = order.get("notes") if isinstance(order.get("notes"), dict) else {}
    order_agent_id = str(notes.get("agent_id") or "")
    if (
        not str(order.get("receipt") or "").startswith("agent_ins_")
        or not order_agent_id.isdigit()
    ):
        logger.error(
            "Insurance payment - order %s is not an insurance agent order", order_id
        )
        raise InsurancePaymentRejected("Payment does not belong to this agent.")
    if agent_id is not None and order_agent_id != str(agent_id):
        # One captured payment could otherwise activate several same-priced agents.
        logger.critical(
            "Insurance payment order %s is not for agent %s", order_id, agent_id
        )
        raise InsurancePaymentRejected("Payment does not belong to this agent.")
    agent = Agent.objects.filter(pk=int(order_agent_id)).first()
    if not agent:
        logger.error(
            "Insurance payment - agent %s of order %s not found",
            order_agent_id,
            order_id,
        )
        raise InsurancePaymentRejected("Agent not found.")
    if agent.status in INSURANCE_PAID_STATUSES:
        if agent.payment_reference != payment_id:
            logger.error(
                "Insurance payment %s for agent %s, already paid by %s: possible double charge",
                payment_id,
                agent.pk,
                agent.payment_reference,
            )
        return agent, False

    payment = captured_insurance_payment(client, order_id, payment_id, payment)
    if (
        AgentSubscription.objects.filter(razorpay_payment_id=payment_id)
        .exclude(agent=agent)
        .exists()
    ):
        logger.critical(
            "Insurance payment %s already used for another agent", payment_id
        )
        raise InsurancePaymentRejected("This payment has already been used.")

    subscription = (
        agent.subscriptions.filter(payment_status="pending")
        .order_by("-created_at")
        .first()
    )
    amount = (
        subscription.registration_amount
        if subscription
        else (2359 if agent.plan_type == "starter" else 8258)
    )
    expected_paise = _expected_amount_paise(amount)
    if not _paise_amounts_match(payment.get("amount"), expected_paise):
        logger.error(
            "Insurance payment - amount mismatch. order=%s payment=%s paid=%s expected=%s",
            order_id,
            payment_id,
            payment.get("amount"),
            expected_paise,
        )
        raise InsurancePaymentRejected("Payment amount mismatch.")

    recorded_by_id = str(notes.get("insurance_user_id") or "")
    recorded_by = (
        User.objects.filter(pk=int(recorded_by_id)).first()
        if recorded_by_id.isdigit()
        else None
    )
    fulfilled = _complete_insurance_agent_payment(agent.pk, payment_id, recorded_by)
    logger.info(
        "Insurance payment - agent %s fulfilled=%s by order %s payment %s",
        agent.pk,
        fulfilled,
        order_id,
        payment_id,
    )
    return agent, fulfilled


@login_required
@insurance_manager_or_accounts_required
def handle_payment_success(request, agent_id):

    company_id = request.user.insurance_profile.get_insurance_company_id()
    agent = get_object_or_404(Agent, id=agent_id, insurance_id=company_id)

    payment_ref = request.POST.get("razorpay_payment_id")
    order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    key = getattr(settings, "RAZORPAY_KEY", "")
    secret = getattr(settings, "RAZORPAY_SECRET", "")
    is_mock_payment = not bool(key and secret and razorpay) and getattr(
        settings, "DEBUG", False
    )

    try:
        if not is_mock_payment:
            if not (key and secret and razorpay):
                return JsonResponse(
                    {"success": False, "message": USER_PAYMENT_UNAVAILABLE}, status=500
                )

            client = razorpay.Client(auth=(key, secret))
            try:
                client.utility.verify_payment_signature(
                    {
                        "razorpay_order_id": order_id,
                        "razorpay_payment_id": payment_ref,
                        "razorpay_signature": signature,
                    }
                )
            except razorpay.errors.SignatureVerificationError:
                return JsonResponse(
                    {"success": False, "message": "Invalid payment signature."},
                    status=400,
                )
            except Exception as e:
                logger.error(
                    "Insurance payment verification failed for agent %s: %s",
                    agent.id,
                    e,
                )
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Failed to verify payment. Please contact support.",
                    },
                    status=400,
                )

            _agent, fulfilled = fulfil_insurance_agent_order(
                order_id, payment_ref, agent_id=agent.id
            )
        else:
            if not getattr(settings, "DEBUG", False):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Mock payments are disabled in production.",
                    },
                    status=403,
                )
            if not payment_ref:
                payment_ref = "TEST_PAY_" + "".join(
                    random.choices(string.ascii_uppercase + string.digits, k=10)
                )
            fulfilled = _complete_insurance_agent_payment(
                agent.id, payment_ref, request.user
            )
    except InsurancePaymentRejected as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    except Exception:
        logger.exception("Insurance payment handling failed for agent %s", agent.id)
        return JsonResponse(
            {
                "success": False,
                "message": "Payment handling failed. Please contact support.",
            },
            status=500,
        )

    if not fulfilled:
        return JsonResponse({"success": True, "redirect_url": "/insurance/payments/"})
    return JsonResponse(
        {
            "success": True,
            "message": "Online payment completed successfully. Agent has been advanced to admin approval.",
            "redirect_url": "/insurance/payments/",
        }
    )
