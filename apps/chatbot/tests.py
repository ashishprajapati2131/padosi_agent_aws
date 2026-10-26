import uuid

from django.test import RequestFactory, SimpleTestCase

from apps.chatbot.views import CHAT_IDS_SESSION_KEY, _issue_chat_id, get_history


class ChatHistoryOwnershipTests(SimpleTestCase):
    def test_history_for_id_not_issued_to_this_session_is_404(self):
        req = RequestFactory().get('/chatbot-api/history/x/')
        req.session = {}
        resp = get_history(req, uuid.uuid4().hex)
        self.assertEqual(resp.status_code, 404)

    def test_issued_ids_are_uuid4_and_remembered(self):
        req = RequestFactory().get('/')
        req.session = {}
        chat_id = _issue_chat_id(req)
        self.assertEqual(uuid.UUID(chat_id).version, 4)
        self.assertEqual(req.session[CHAT_IDS_SESSION_KEY], [chat_id])
