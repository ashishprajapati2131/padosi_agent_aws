"""Event-day end-to-end journeys (Paldi 48-hour challenge, referrals, normal
signup, payment, admin approval), driven through the real URLs, views,
middleware and templates. Only Razorpay and email are mocked."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import Client, RequestFactory

from apps.agents.models import Agent, AgentSubscription
from apps.agents.signup_test_support import _SignupBase, _captured_webhook, _rzp
from apps.agents.test_registration_e2e import _no_favorites   # test-DB copy of a Laravel table
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant

EMAIL = 'apps.agents.services.brevo.email_service'
QUEUE = 'apps.agents.views.registration.queue_invoice_and_welcome'
RZP = 'apps.agents.views.registration.razorpay_client'


class EventDayJourneyTests(_SignupBase):
    def setUp(self):
        super().setUp()
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=2, window_hours=48)
        self._n = 0

    # ── helpers ──────────────────────────────────────────────────────────
    def _dashboard(self, client):
        with _no_favorites():
            return client.get('/agent/dashboard/')

    def _form(self, email, mobile):
        return {'fullname': 'Event Person', 'email': email, 'mobile': mobile, 'whatsapp': mobile,
                'agent_pincode': '380001', 'state': 'Gujarat', 'experience_range': '3',
                'segments[]': ['life'], 'client_base': '100', 'agree_terms': 'on'}

    def _stall_signup(self, client, email, mobile):
        """Paldi stall: open the event page, submit step 1."""
        page = client.get('/48HR/')
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['event_referral_mode'])
        with patch(EMAIL) as mail:
            mail.send_welcome.return_value = True
            r = client.post('/agent-register-step1/', self._form(email, mobile))
        return r

    def _ids(self):
        self._n += 1
        return f'order_EVDAY{self._n:09d}', f'pay_EVDAY{self._n:010d}'

    def _paid_signup(self, client, email, mobile, plan='starter', via='callback', entry=None):
        """Normal paid signup in its own browser, optionally from a link."""
        if entry:
            r = client.get(entry, follow=True)
            self.assertEqual(r.status_code, 200, entry)
        r = client.post('/agent-register-step1/', self._form(email, mobile))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'], r.json())
        self.assertEqual(r.json().get('redirect'), '/chooseplan/')
        client.post('/agent-register-step2/', {'bio': 'x'})
        self.assertEqual(client.get('/chooseplan/').status_code, 200)
        order_id, pay_id = self._ids()
        with patch('apps.agents.views.registration.create_checkout_order', return_value=(order_id, False)):
            r = client.post('/agent-register/complete/', data={'plan_type': plan}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        sub = AgentSubscription.objects.get(razorpay_order_id=order_id)
        paise = self._paise(sub)
        with patch(QUEUE), patch(RZP, return_value=_rzp(paise)):
            if via == 'callback':
                r = client.post('/agent-register/verify-payment/', data={
                    'razorpay_order_id': order_id, 'razorpay_payment_id': pay_id, 'razorpay_signature': 'sig'},
                    content_type='application/json')
                self.assertTrue(r.json()['success'], r.json())
            else:   # customer closed the browser: only Razorpay's webhook arrives
                body = json.loads(_captured_webhook(order_id, paise))
                body['payload']['payment']['entity']['id'] = pay_id
                with patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
                    r = Client().post('/razorpay-webhook/', data=json.dumps(body),
                                      content_type='application/json', HTTP_X_RAZORPAY_SIGNATURE='sig')
                self.assertEqual(r.status_code, 200, r.content)
        agent = Agent.objects.get(email=email)
        return agent, sub, order_id, pay_id

    def _admin_set_status(self, agent, status):
        from apps.admin_panel.views.agents import toggle_status
        request = RequestFactory().post('/admin/agents/toggle-status/', content_type='application/json',
                                        data=json.dumps({'id': agent.pk, 'status': status}))
        request.session = {}
        request.admin_user = SimpleNamespace(role='staff', permissions=['approvals_awaiting_verification'])
        with patch('apps.admin_panel.views.agents._get_admin_from_session', return_value=1):
            resp = toggle_status(request)
        self.assertTrue(json.loads(resp.content)['success'], resp.content)
        agent.refresh_from_db()
        return agent

    # ── journeys ─────────────────────────────────────────────────────────
    def test_paldi_challenge_from_stall_to_win_and_approval(self):
        stall = Client()
        r = self._stall_signup(stall, 'challenger@example.com', '9811111111')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()['success'], r.json())
        challenger = Agent.objects.get(email='challenger@example.com')
        participant = EventReferralParticipant.objects.get(agent=challenger)
        self.assertEqual(challenger.status, 'event_challenge')
        self.assertEqual(participant.status, EventReferralParticipant.STATUS_ACTIVE)
        self.assertTrue(participant.referral_code.startswith('EV-'))
        hours = (participant.deadline_at - datetime.now()).total_seconds() / 3600
        self.assertAlmostEqual(hours, 48, delta=0.1)

        # Challenger is logged in and sees the dashboard; public leaderboard works.
        self.assertEqual(self._dashboard(stall).status_code, 200)
        self.assertEqual(Client().get('/48HR/leaderboard/').status_code, 200)

        # Two friends pay through the challenger's link: one in the browser,
        # one where only the webhook arrives.
        code = participant.referral_code
        a1, *_ = self._paid_signup(Client(), 'friend1@example.com', '9822222221', entry=f'/join/{code}/')
        participant.refresh_from_db()
        self.assertEqual(a1.referred_by_code, code)
        self.assertEqual(a1.status, 'pending_approval')
        self.assertEqual(participant.paid_count, 1)
        self.assertEqual(participant.status, EventReferralParticipant.STATUS_ACTIVE)

        a2, *_ = self._paid_signup(Client(), 'friend2@example.com', '9822222222',
                                   plan='professional', via='webhook', entry=f'/join/{code}/')
        participant.refresh_from_db()
        challenger.refresh_from_db()
        self.assertEqual(a2.status, 'pending_approval')
        self.assertEqual(participant.paid_count, 2)
        self.assertEqual(participant.status, EventReferralParticipant.STATUS_WON)
        self.assertEqual((challenger.status, challenger.plan_type), ('pending_approval', 'basic'))

        # Winner and the paying friends wait in Admin -> Approvals; approve them.
        for agent in (challenger, a1, a2):
            self.assertEqual(self._admin_set_status(agent, 'active').status, 'active')
        self.assertEqual(self._dashboard(stall).status_code, 200)

    def test_same_payment_twice_counts_once(self):
        stall = Client()
        self._stall_signup(stall, 'twice@example.com', '9811111112')
        participant = EventReferralParticipant.objects.get(agent__email='twice@example.com')
        client = Client()
        friend, sub, order_id, pay_id = self._paid_signup(
            client, 'twice.friend@example.com', '9822222223', entry=f'/join/{participant.referral_code}/')
        paise = self._paise(sub)
        with patch(QUEUE), patch(RZP, return_value=_rzp(paise)), \
             patch('apps.agents.views.registration.razorpay_webhook_secret', return_value='whsec'):
            client.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': order_id, 'razorpay_payment_id': pay_id, 'razorpay_signature': 'sig'},
                content_type='application/json')
            body = json.loads(_captured_webhook(order_id, paise))
            body['payload']['payment']['entity']['id'] = pay_id
            Client().post('/razorpay-webhook/', data=json.dumps(body), content_type='application/json',
                          HTTP_X_RAZORPAY_SIGNATURE='sig')
        participant.refresh_from_db()
        self.assertEqual(participant.paid_count, 1)
        self.assertEqual(AgentSubscription.objects.filter(agent=friend, payment_status='completed').count(), 1)

    def test_challenger_using_own_mobile_does_not_count(self):
        self._stall_signup(Client(), 'cheat@example.com', '9811111113')
        participant = EventReferralParticipant.objects.get(agent__email='cheat@example.com')
        # One mobile, one account (audit L3): the second signup is refused at step 1.
        client = Client()
        client.get(f'/join/{participant.referral_code}/', follow=True)
        r = client.post('/agent-register-step1/', self._form('cheat.alt@example.com', '9811111113'))
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(Agent.objects.filter(email='cheat.alt@example.com').exists())
        participant.refresh_from_db()
        self.assertEqual(participant.paid_count, 0)

    def test_48_hours_pass_then_challenger_buys_a_plan(self):
        stall = Client()
        self._stall_signup(stall, 'late@example.com', '9811111114')
        participant = EventReferralParticipant.objects.get(agent__email='late@example.com')
        participant.deadline_at = datetime.now() - timedelta(minutes=1)
        participant.save(update_fields=['deadline_at'])

        # Opening the dashboard after the deadline blocks the challenge.
        self.assertEqual(self._dashboard(stall).status_code, 200)
        participant.refresh_from_db()
        self.assertEqual(participant.status, EventReferralParticipant.STATUS_BLOCKED)

        # A referral paying after the deadline does not count.
        self._paid_signup(Client(), 'late.friend@example.com', '9822222224', entry=f'/join/{participant.referral_code}/')
        participant.refresh_from_db()
        self.assertEqual(participant.paid_count, 0)

        # The challenger can still buy a plan and reaches Approvals.
        self.assertEqual(stall.get('/chooseplan/').status_code, 200)
        order_id, pay_id = self._ids()
        with patch('apps.agents.views.registration.create_checkout_order', return_value=(order_id, False)):
            r = stall.post('/agent-register/complete/', data={'plan_type': 'starter'}, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        sub = AgentSubscription.objects.get(razorpay_order_id=order_id)
        with patch(QUEUE), patch(RZP, return_value=_rzp(self._paise(sub))):
            r = stall.post('/agent-register/verify-payment/', data={
                'razorpay_order_id': order_id, 'razorpay_payment_id': pay_id, 'razorpay_signature': 'sig'},
                content_type='application/json')
        self.assertTrue(r.json()['success'], r.json())
        agent = Agent.objects.get(email='late@example.com')
        self.assertEqual((agent.status, agent.plan_type), ('pending_approval', 'starter'))

    def test_expiry_job_blocks_challengers_who_never_return(self):
        from django.core.management import call_command
        self._stall_signup(Client(), 'gone@example.com', '9811111115')
        participant = EventReferralParticipant.objects.get(agent__email='gone@example.com')
        participant.deadline_at = datetime.now() - timedelta(minutes=1)
        participant.save(update_fields=['deadline_at'])
        call_command('process_event_referral_expirations', stdout=MagicMock())
        participant.refresh_from_db()
        self.assertEqual(participant.status, EventReferralParticipant.STATUS_BLOCKED)

    def test_already_registered_people_are_sent_to_login(self):
        self._paid_signup(Client(), 'paid.before@example.com', '9822222225')
        r = self._stall_signup(Client(), 'paid.before@example.com', '9822222225')
        self.assertIn(r.status_code, (200, 422))
        self.assertFalse(r.json().get('success'), r.json())
        self.assertFalse(EventReferralParticipant.objects.filter(agent__email='paid.before@example.com').exists())

    def test_event_closed_by_admin_refuses_new_challengers(self):
        self.campaign.is_enabled = False
        self.campaign.save()
        client = Client()
        page = client.get('/48HR/')
        self.assertTrue(page.context['registration_closed'])
        r = client.post('/agent-register-step1/', self._form('closed@example.com', '9811111116'))
        self.assertFalse(EventReferralParticipant.objects.filter(agent__email='closed@example.com').exists())
        self.assertEqual(r.status_code, 200)   # plain signup (flag not set), not a challenge

    def test_normal_signup_payment_and_approval(self):
        client = Client()
        agent, sub, *_ = self._paid_signup(client, 'normal@example.com', '9833333331', entry='/agent-registration/')
        sub.refresh_from_db()
        self.assertEqual((agent.status, sub.payment_status), ('pending_approval', 'completed'))
        self.assertEqual(self._admin_set_status(agent, 'active').status, 'active')
        self.assertEqual(self._dashboard(client).status_code, 200)

    def test_professional_signup_via_webhook_only(self):
        agent, sub, *_ = self._paid_signup(Client(), 'pro.webhook@example.com', '9833333332',
                                           plan='professional', via='webhook')
        sub.refresh_from_db()
        self.assertEqual((agent.status, agent.plan_type, sub.payment_status),
                         ('pending_approval', 'professional', 'completed'))

    def test_championship_and_unknown_links_do_not_break(self):
        from apps.referral_championship.models import ChampionshipParticipant
        self.assertIn(Client().get('/join/PA-NOSUCH/').status_code, (200, 302))
        self.assertIn(Client().get('/join/NOSUCHCODE/').status_code, (200, 302))
        self.assertIn(Client().get('/agent-registration/join/EV-NOSUCH/').status_code, (200, 302))
        self.assertTrue(ChampionshipParticipant)   # model import works
