from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.admin_panel.models.contact_submission import ContactSubmission


class ContactRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def _post(self):
        return self.client.post(
            reverse("home:contact_submit"),
            {
                "name": "Asha Shah",
                "mobile": "9876500000",
                "email": "asha@example.com",
                "subject": "Policy question",
                "message": "Please call me about a health plan.",
            },
        )

    def test_sixth_message_in_an_hour_gets_429(self):
        for i in range(5):
            self.assertEqual(self._post().status_code, 200, i)
        blocked = self._post()
        self.assertEqual(blocked.status_code, 429)
        self.assertFalse(blocked.json()["success"])
        self.assertEqual(ContactSubmission.objects.count(), 5)

    def test_invalid_submissions_count_toward_the_limit(self):
        for _ in range(5):
            self.client.post(reverse("home:contact_submit"), {"name": "x"})
        self.assertEqual(self._post().status_code, 429)
