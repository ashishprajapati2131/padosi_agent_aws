import razorpay
from fastapi_app.config import settings
from padosi_agent.razorpay_env import USER_PAYMENT_UNAVAILABLE
import logging

logger = logging.getLogger(__name__)

def check_order_payment_status(order_id: str) -> dict:
    """
    Checks the status of payments associated with a Razorpay order_id.
    Uses settings.RAZORPAY_KEY and settings.RAZORPAY_SECRET.
    """
    key_id = settings.RAZORPAY_KEY
    key_secret = settings.RAZORPAY_SECRET

    if not key_id or not key_secret:
        logger.error("Razorpay keys are not configured in settings.")
        return {"status": "error", "message": USER_PAYMENT_UNAVAILABLE}

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        payments = client.order.payments(order_id)
    except razorpay.errors.BadRequestError as e:
        logger.error(f"Razorpay BadRequestError for order {order_id}: {e}")
        return {"status": "error", "message": USER_PAYMENT_UNAVAILABLE}
    except Exception as e:
        logger.error(f"Razorpay API error for order {order_id}: {e}")
        return {"status": "error", "message": USER_PAYMENT_UNAVAILABLE}

    if not payments or "items" not in payments or not payments["items"]:
        return {"status": "not_attempted"}

    # Look for a captured payment first
    for p in payments["items"]:
        if p.get("status") == "captured":
            return {
                "status": "paid",
                "payment_id": p["id"],
                "amount": p["amount"] / 100,
                "method": p.get("method"),
            }

    # Check for authorized payments or other statuses
    for p in payments["items"]:
        if p.get("status") == "authorized":
            return {"status": "authorized_not_captured", "payment_id": p["id"]}
        if p.get("status") == "failed":
            return {"status": "failed", "payment_id": p["id"], "error": p.get("error_description")}

    return {"status": "pending"}
