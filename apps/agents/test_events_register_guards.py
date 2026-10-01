"""Audit 2026-10-01 F-03: the legacy /events/ register view (currently
unreachable: its URL duplicates the form's, and it is otherwise broken) would
rewrite any agent not active / pending and accept staff emails. It now has the
main signup's guards, so re-routing it later cannot reopen a takeover."""
from datetime import date

from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.agents.models import Agent, Event


class EventsRegisterGuardTests(TestCase):
    def setUp(self):
        Event.objects.create(name='Expo', event_date=date.today())

    def _register(self, email, fullname='Event Agent'):
        from apps.agents.views.events import register
        request = RequestFactory().post('/events/register/', {
            'fullname': fullname, 'email': email, 'mobile': '9876543210',
            'insurance_segments': ['life'], 'pincode': '380001'})
        request._dont_enforce_csrf_checks = True
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        request.user = type('Anon', (), {'is_authenticated': False})()
        resp = register(request)
        self.last_messages = [str(m) for m in request._messages]
        return resp

    def test_suspended_agent_is_not_rewritten(self):
        agent = Agent.objects.create(fullname='Original', email='susp.event@example.com', mobile='9000000201',
                                     status='suspended')
        self._register(agent.email, fullname='Attacker')
        agent.refresh_from_db()
        self.assertEqual((agent.fullname, agent.status), ('Original', 'suspended'))

    def test_staff_email_is_refused(self):
        User.objects.create_user('boss.event', 'boss.event@example.com', 'x', is_staff=True)
        self._register('boss.event@example.com')
        self.assertFalse(Agent.objects.filter(email='boss.event@example.com').exists())
