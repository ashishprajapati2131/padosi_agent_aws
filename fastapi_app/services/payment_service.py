import hmac
import hashlib
import json
import base64
import urllib.request
import urllib.error
from typing import Optional, Dict
from app.config import settings

class PaymentService:
    @staticmethod
    def create_order(amount_paise: int, receipt: str) -> Optional[Dict]:
        """
        Calls Razorpay REST API to create an order.
        Avoids external SDK dependency using urllib.request.
        """
        url = "https://api.razorpay.com/v1/orders"
        data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "payment_capture": 1
        }
        
        # Build Authorization header (Basic auth: key_id:key_secret)
        auth_str = f"{settings.RAZORPAY_KEY}:{settings.RAZORPAY_SECRET}"
        auth_bytes = auth_str.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_b64}"
        }
        
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode("utf-8"), 
            headers=headers,
            method="POST"
        )
        
        try:
            # Bypass SSL certificate check in dev environments if needed,
            # but standard urllib request works by default.
            with urllib.request.urlopen(req) as response:
                res_body = response.read().decode("utf-8")
                return json.loads(res_body)
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            print(f"Razorpay API Error ({e.code}): {error_body}")
            return None
        except Exception as ex:
            print(f"Razorpay Connection Error: {ex}")
            return None

    @staticmethod
    def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
        """
        Verifies the Razorpay payment signature using SHA256 HMAC.
        """
        if not signature or not settings.RAZORPAY_SECRET:
            return False
        
        msg = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            key=settings.RAZORPAY_SECRET.encode("utf-8"),
            msg=msg.encode("utf-8"),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(generated_signature, signature)

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str) -> bool:
        """
        Verifies Razorpay webhook signature.
        """
        if not signature or not settings.RAZORPAY_WEBHOOK_SECRET:
            return False
            
        generated_signature = hmac.new(
            key=settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(generated_signature, signature)
