"""Write flows for admin subscriptions (views/subscriptions.py)."""

from apps.agents.models import PaymentStatus


def delete_unpaid_subscription(subscription):
    """Delete the row and return True; return False (nothing deleted) if it is paid."""
    # Paid rows are GST/payment records and keep the Razorpay order findable (CLAUDE.md invariant 9).
    if (
        subscription.payment_status == PaymentStatus.COMPLETED
        or subscription.razorpay_payment_id
    ):
        return False
    subscription.delete()
    return True
