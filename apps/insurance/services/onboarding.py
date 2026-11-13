"""Shared row creation for agents onboarded through the insurance portal."""

from django.contrib.auth.models import User

from apps.agents.models import Agent, AgentProfile, AgentSubscription
from apps.agents.services.feature_unlock import PLAN_LABELS


def create_onboarded_agent(
    *,
    company_id,
    onboarded_by,
    fullname,
    email,
    mobile,
    plan_type,
    agent_pincode,
    state,
    amount,
    agent_status,
    payment_status,
    starts_at,
    expires_at,
    razorpay_order_id,
    agent_fields=None,
    subscription_fields=None,
):
    """Create the auth User, Agent, AgentProfile and AgentSubscription of one agent.

    Callers own validation, the transaction and error handling. ``agent_fields`` /
    ``subscription_fields`` carry the per-path extras (offline payment details,
    Razorpay payment id / signature). Returns the Agent.
    """
    # Insurance-portal onboarding keeps email-as-password (CLAUDE.md invariant 3).
    new_user = User.objects.create_user(
        username=email,
        email=email,
        password=email,
        first_name=fullname,
        is_active=False,
    )

    agent = Agent.objects.create(
        user=new_user,
        insurance_id=company_id,
        onboarded_by=onboarded_by,
        fullname=fullname,
        email=email,
        mobile=mobile,
        status=agent_status,
        plan_type=plan_type,
        registration_step=2,
        **(agent_fields or {}),
    )

    AgentProfile.objects.create(
        agent=agent,
        address="Pincode: " + agent_pincode,
        state=state,
    )

    AgentSubscription.objects.create(
        agent=agent,
        selected_plan=PLAN_LABELS["professional"]
        if plan_type == "professional"
        else PLAN_LABELS["starter"],
        registration_amount=amount,
        payment_status=payment_status,
        status="inactive",
        starts_at=starts_at,
        expires_at=expires_at,
        razorpay_order_id=razorpay_order_id,
        **(subscription_fields or {}),
    )
    return agent
