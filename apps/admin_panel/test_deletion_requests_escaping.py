"""H3: deletion-request fields come from a public form and were embedded in a
<script> block via json.dumps(...)|safe, so `</script>` broke out of it."""
from unittest.mock import patch

from django.test import RequestFactory, TestCase

from apps.agents.models import AccountDeletionRequest

PAYLOAD = '</script><script>alert(1)</script>'


class DeletionRequestListEscapingTests(TestCase):
    def test_script_payload_in_reason_is_escaped(self):
        from apps.admin_panel.views.account_deletion import deletion_requests_list
        AccountDeletionRequest.objects.create(reference_id='DEL-XSS-1', identifier=PAYLOAD, reason=PAYLOAD)
        request = RequestFactory().get('/admin/deletion-requests/')
        request.session = {}
        with patch('apps.admin_panel.views.account_deletion._get_admin_from_session', return_value=1):
            html = deletion_requests_list(request).content.decode()
        self.assertNotIn(PAYLOAD, html)
        self.assertIn('\\u003C/script\\u003E\\u003Cscript\\u003Ealert(1)', html)
        self.assertIn('function esc(v)', html)
