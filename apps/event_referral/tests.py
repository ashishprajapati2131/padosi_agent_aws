from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from apps.agents.models import Agent, AgentSubscription
from apps.event_referral.models import EventReferral, EventReferralCampaign, EventReferralParticipant
from apps.event_referral.services.participant_service import (
    evaluate_participant,
    event_referral_bypasses_championship_unlock,
    event_referral_effective_plan_type,
    event_referral_grants_dashboard,
    force_lock_all_dashboard_features,
)
from apps.event_referral.services.qualification_service import (
    is_event_referral_code,
    qualify_event_referral,
    register_referred_agent,
)
from apps.agents.services.account_auth import agent_can_access_dashboard


class EventReferralRegistrationTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(is_enabled=True)

    def test_event_page_uses_agent_registration_template(self):
        client = Client()
        resp = client.get(reverse('event_referral:register'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'agents/registration.html')
        self.assertTrue(resp.context['event_referral_mode'])

    def test_event_page_og_image_meta(self):
        client = Client()
        resp = client.get(reverse('event_referral:register'))
        self.assertTrue(resp.context.get('use_paldi_og'))
        og_url = resp.context.get('paldi_og_image_url', '')
        self.assertIn('paldi_48hr_championship_og.jpg', og_url)
        self.assertIn(og_url, resp.content.decode())

    @patch('apps.agents.services.brevo.email_service')
    def test_step1_finalize_creates_challenge_agent(self, mock_email):
        mock_email.send_welcome.return_value = True
        client = Client()
        session = client.session
        session['event_referral_registration'] = True
        session.save()

        resp = client.post(
            reverse('agents:agent_register_step1'),
            {
                'fullname': 'Test Agent',
                'email': 'evtest@example.com',
                'mobile': '9876543210',
                'whatsapp': '9876543210',
                'agent_pincode': '380001',
                'state': 'Gujarat',
                'experience_range': '3',
                'segments[]': ['life'],
                'client_base': '100',
                'agree_terms': 'on',
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))
        agent = Agent.objects.get(email='evtest@example.com')
        self.assertEqual(agent.status, 'event_challenge')
        self.assertTrue(agent_can_access_dashboard(agent))
        self.assertTrue(EventReferralParticipant.objects.filter(agent=agent).exists())
        mock_email.send_welcome.assert_called_once()
        welcome_kwargs = mock_email.send_welcome.call_args.kwargs
        welcome_args = mock_email.send_welcome.call_args.args
        self.assertEqual(welcome_args[0], 'evtest@example.com')
        self.assertEqual(welcome_args[2], '9876543210')
        self.assertEqual(welcome_kwargs.get('subject'), 'Welcome to Paldi — your PadosiAgent login details')

    def test_ev_code_detection(self):
        self.assertTrue(is_event_referral_code('EV-ABC123'))
        self.assertFalse(is_event_referral_code('PA-ABC123'))

    def test_active_challenge_uses_professional_trial_not_lock(self):
        agent = Agent.objects.create(
            fullname='Trial Agent',
            email='trial@example.com',
            mobile='9000000010',
            status='event_challenge',
            plan_type='',
        )
        participant = EventReferralParticipant.create_for_agent(agent, self.campaign)
        self.assertEqual(event_referral_effective_plan_type(agent, participant), 'professional')
        self.assertFalse(force_lock_all_dashboard_features(participant))
        participant.status = EventReferralParticipant.STATUS_BLOCKED
        self.assertTrue(force_lock_all_dashboard_features(participant))

    def test_public_leaderboard_ranks_by_paid_count(self):
        from apps.event_referral.services.public_leaderboard import get_public_leaderboard_payload

        a1 = Agent.objects.create(
            fullname='Leader Alpha',
            email='alpha@example.com',
            mobile='9000000101',
            status='event_challenge',
        )
        a2 = Agent.objects.create(
            fullname='Leader Beta',
            email='beta@example.com',
            mobile='9000000102',
            status='event_challenge',
        )
        p1 = EventReferralParticipant.create_for_agent(a1, self.campaign)
        p2 = EventReferralParticipant.create_for_agent(a2, self.campaign)
        p1.paid_count = 3
        p1.save(update_fields=['paid_count'])
        p2.paid_count = 7
        p2.save(update_fields=['paid_count'])

        payload = get_public_leaderboard_payload(limit=10)
        self.assertGreaterEqual(len(payload['leaderboard']), 2)
        self.assertEqual(payload['leaderboard'][0]['name'], 'Leader Beta')
        self.assertEqual(payload['leaderboard'][0]['paid_count'], 7)
        self.assertEqual(payload['top_three'][0]['rank'], 1)

    def test_public_leaderboard_page_is_public(self):
        client = Client()
        resp = client.get('/event-registration/leaderboard/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'brand-logo')
        self.assertContains(resp, 'Padosi')
        self.assertContains(resp, 'LEADERBOARD')
        self.assertContains(resp, 'col-first')
        self.assertContains(resp, 'col-second')
        self.assertContains(resp, 'col-third')
        self.assertNotContains(resp, 'paldi_leaderboard_hero.jpg')
        self.assertNotContains(resp, 'Latest referrals')
        self.assertNotContains(resp, 'Challengers')
        resp2 = client.get('/stall-leaderboard/')
        self.assertEqual(resp2.status_code, 200)

    def test_public_leaderboard_referrals_newest_first(self):
        from apps.event_referral.services.public_leaderboard import get_public_leaderboard_payload

        agent = Agent.objects.create(
            fullname='Sort Host',
            email='sort-host@example.com',
            mobile='9000000201',
            status='event_challenge',
        )
        participant = EventReferralParticipant.create_for_agent(agent, self.campaign)
        participant.paid_count = 2
        participant.save(update_fields=['paid_count'])
        now = datetime.now()
        older = Agent.objects.create(
            fullname='Old Ref',
            email='old-ref@example.com',
            mobile='9000000202',
            status='pending_approval',
        )
        newer = Agent.objects.create(
            fullname='New Ref',
            email='new-ref@example.com',
            mobile='9000000203',
            status='pending_approval',
        )
        EventReferral.objects.create(
            participant=participant,
            referred_agent=older,
            state=EventReferral.STATE_PAID,
            counts=True,
            registered_at=now - timedelta(hours=10),
            paid_at=now - timedelta(hours=8),
            snapshot_name='Older Person',
        )
        EventReferral.objects.create(
            participant=participant,
            referred_agent=newer,
            state=EventReferral.STATE_PAID,
            counts=True,
            registered_at=now - timedelta(hours=2),
            paid_at=now - timedelta(hours=1),
            snapshot_name='Newest Person',
        )
        payload = get_public_leaderboard_payload(limit=5)
        row = next(r for r in payload['leaderboard'] if r['agent_id'] == agent.id)
        names = [item['name'] for item in row['referrals']]
        self.assertEqual(names[0], 'Newest Person')
        self.assertEqual(names[1], 'Older Person')

    def test_event_referral_championship_funnel_context(self):
        from apps.event_referral.services.championship_dashboard import (
            build_event_referral_championship_context,
        )
        from django.test import RequestFactory

        agent = Agent.objects.create(
            fullname='Champ Bridge',
            email='champbridge@example.com',
            mobile='9000000030',
            status='event_challenge',
            plan_type='',
        )
        participant = EventReferralParticipant.create_for_agent(agent, self.campaign)
        request = RequestFactory().get('/agent/championship/agent/dashboard/')
        ctx = build_event_referral_championship_context(
            request, agent, lambda p: f'https://example.com{p}',
        )
        self.assertTrue(ctx['event_referral_mode'])
        self.assertEqual(ctx['display_referral_id'], participant.referral_code)
        self.assertIn(participant.referral_code, ctx['referral_url'])

    def test_event_challenger_bypasses_championship_profile_review_gate(self):
        agent = Agent.objects.create(
            fullname='Champ Bypass',
            email='champbypass@example.com',
            mobile='9000000020',
            status='event_challenge',
            plan_type='',
        )
        EventReferralParticipant.create_for_agent(agent, self.campaign)
        self.assertTrue(event_referral_bypasses_championship_unlock(agent))

        plain = Agent.objects.create(
            fullname='Plain Agent',
            email='plain@example.com',
            mobile='9000000021',
            status='active',
            plan_type='starter',
        )
        self.assertFalse(event_referral_bypasses_championship_unlock(plain))


class EventReferralQualificationTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        self.campaign = EventReferralCampaign.objects.create(
            is_enabled=True,
            required_paid_referrals=2,
            window_hours=48,
        )
        self.referrer = Agent.objects.create(
            fullname='Referrer',
            email='referrer@example.com',
            mobile='9000000001',
            status='event_challenge',
            plan_type='',
        )
        self.participant = EventReferralParticipant.create_for_agent(self.referrer, self.campaign)
        self.participant.required_paid_referrals = 2
        self.participant.save()

    def _paid_agent(self, email, mobile):
        return Agent.objects.create(
            fullname='Ref',
            email=email,
            mobile=mobile,
            status='pending_approval',
            plan_type='basic',
            referred_by_code=self.participant.referral_code,
        )

    def _subscription(self, agent):
        return AgentSubscription.objects.create(
            agent=agent,
            selected_plan='Starter',
            registration_amount=100,
            payment_status='completed',
            status='active',
            razorpay_order_id='order_test123456',
            razorpay_payment_id='pay_test1234567',
        )

    def test_paid_referrals_grant_basic_plan(self):
        for i in range(2):
            agent = self._paid_agent(f'ref{i}@example.com', f'900000000{i+2}')
            register_referred_agent(agent)
            qualify_event_referral(agent, self._subscription(agent))
        self.participant.refresh_from_db()
        self.referrer.refresh_from_db()
        self.assertEqual(self.participant.status, 'won')
        self.assertEqual(self.referrer.plan_type, 'basic')

    def test_late_payment_does_not_count(self):
        self.participant.deadline_at = datetime.now() - timedelta(hours=1)
        self.participant.save()
        agent = self._paid_agent('late@example.com', '9000000099')
        register_referred_agent(agent)
        qualify_event_referral(agent, self._subscription(agent))
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.paid_count, 0)
        evaluate_participant(self.participant, block_on_expire=True)
        self.referrer.refresh_from_db()
        self.assertEqual(self.referrer.status, 'pending_payment')
        self.assertTrue(event_referral_grants_dashboard(self.referrer))
        self.assertTrue(force_lock_all_dashboard_features(self.participant))

    def test_self_referral_rejected(self):
        self.referrer.referred_by_code = self.participant.referral_code
        self.referrer.save()
        register_referred_agent(self.referrer)
        self.assertFalse(
            self.participant.referrals.filter(referred_agent=self.referrer, state='paid').exists()
        )
