import json
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from apps.admin_panel.models import ContactSubmission


class QuickLeadCaptureWhiteBoxTests(TestCase):
    """
    White-Box Unit and Boundary Tests for `quick_lead_capture` endpoint (/api/quick-lead-capture/).
    Covers request method enforcement, payload sanitization, phone digit validation, and database records.
    """

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.url = reverse("home:quick_lead_capture")

    def test_get_method_rejected(self):
        """HTTP Contract: GET request must return 405 Method Not Allowed."""
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_successful_lead_capture(self):
        """Positive test: Valid submission creates ContactSubmission record and returns 200."""
        payload = {
            "name": "Rajesh Kumar",
            "mobile": "9876543210",
            "pincode": "380015",
            "insurance_type": "Health Insurance",
        }
        resp = self.client.post(self.url, data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")

        # Verify database record
        sub = ContactSubmission.objects.filter(mobile="9876543210").first()
        self.assertIsNotNone(sub)
        self.assertEqual(sub.name, "Rajesh Kumar")
        self.assertEqual(sub.email, "lead_9876543210@padosiagent.com")
        self.assertIn("Health Insurance", sub.subject)
        self.assertIn("380015", sub.message)
        self.assertEqual(sub.status, "pending")

    def test_missing_name_rejected(self):
        """Negative test: Missing name returns 400 Bad Request."""
        payload = {
            "name": "",
            "mobile": "9876543210",
        }
        resp = self.client.post(self.url, data=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("required", data["message"].lower())

    def test_missing_mobile_rejected(self):
        """Negative test: Missing mobile number returns 400 Bad Request."""
        payload = {
            "name": "Rajesh Kumar",
            "mobile": "",
        }
        resp = self.client.post(self.url, data=payload)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("required", data["message"].lower())

    def test_invalid_short_mobile_rejected(self):
        """Boundary: Mobile number with fewer than 10 digits returns 400."""
        for short in ["98765", "123456789", "abc"]:
            with self.subTest(mobile=short):
                payload = {
                    "name": "Rajesh Kumar",
                    "mobile": short,
                }
                resp = self.client.post(self.url, data=payload)
                self.assertEqual(resp.status_code, 400)
                data = resp.json()
                self.assertIn("valid 10-digit", data["message"].lower())

    def test_mobile_formatting_and_sanitization(self):
        """Data Flow: Non-digit characters in mobile are stripped clean."""
        payload = {
            "name": "Amit Shah",
            "mobile": "+91 (982) 500-1122",
            "pincode": "395001",
        }
        resp = self.client.post(self.url, data=payload)
        self.assertEqual(resp.status_code, 200)

        sub = ContactSubmission.objects.filter(name="Amit Shah").first()
        self.assertIsNotNone(sub)
        self.assertEqual(len(sub.mobile), 10)
        self.assertTrue(sub.mobile.isdigit())

    def test_long_name_truncated_gracefully(self):
        """Boundary: Name exceeding 100 characters is safely truncated to 100 without DB error."""
        long_name = "X" * 150
        payload = {
            "name": long_name,
            "mobile": "9879001122",
        }
        resp = self.client.post(self.url, data=payload)
        self.assertEqual(resp.status_code, 200)

        sub = ContactSubmission.objects.filter(mobile="9879001122").first()
        self.assertIsNotNone(sub)
        self.assertEqual(len(sub.name), 100)

    def test_rate_limiting_enforced_after_five_requests(self):
        """Security: 6th request from the same IP within the window receives HTTP 429 Too Many Requests."""
        payload = {
            "name": "Throttled User",
            "mobile": "9898989898",
            "insurance_type": "Motor",
        }
        # First 5 submissions succeed
        for i in range(5):
            resp = self.client.post(self.url, data=payload)
            self.assertEqual(resp.status_code, 200, f"Submission {i+1} should succeed")

        # 6th submission should be throttled
        throttled_resp = self.client.post(self.url, data=payload)
        self.assertEqual(throttled_resp.status_code, 429)
        data = throttled_resp.json()
        self.assertEqual(data["status"], "error")
        self.assertIn("too many requests", data["message"].lower())


