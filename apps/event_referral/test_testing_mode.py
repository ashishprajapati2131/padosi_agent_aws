"""Admin testing mode on the live site: a Super Admin switch (auto-off after
2 hours) for fake Paldi/championship referrals. Test data never calls
Razorpay and never gets an invoice, so the invoice number sequence is safe."""
import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.cache import cache
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.agents.models import Agent, AgentSubscription, Invoice
from apps.agents.services.background_jobs import retry_missing_invoices
from apps.agents.services.invoice import invoice_service
from apps.agents.services.post_payment import fulfill_invoice_and_welcome
from apps.event_referral.models import EventReferralCampaign, EventReferralParticipant
from apps.event_referral.views import admin_views
from apps.home.models import SiteSetting
from apps.home.services.agent_filters import listed_agents_queryset
from apps.referral_championship.models import (
    ChampionshipCampaign, ChampionshipParticipant, ChampionshipRewardClaim, ChampionshipRewardSlab,
)

SUPER = SimpleNamespace(role='super')
STAFF = SimpleNamespace(role='staff')


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver', 'localhost'])
class LiveTestingModeTests(TestCase):
    def setUp(self):
        cache.clear()   # SiteSetting values are cached
        EventReferralCampaign.objects.all().delete()
        campaign = EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=5, window_hours=48)
        self.challenger = Agent.objects.create(fullname='Challenger', email='live.tm@example.com',
                                               mobile='9000001501', status='event_challenge', plan_type='')
        self.participant = EventReferralParticipant.create_for_agent(self.challenger, campaign)
        champ = ChampionshipCampaign.get_current()
        ChampionshipRewardSlab.objects.get_or_create(
            campaign=champ, threshold=5,
            defaults={'reward_type': 'membership_fee_back', 'title': 'Fee Back', 'value': 1999, 'is_active': True})

    def _post(self, view, admin, *args, **post):
        request = RequestFactory().post('/admin/event-referral/x/', post)
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        request.admin_user = admin
        with patch('apps.event_referral.views.admin_views._get_admin_from_session', return_value=1):
            return view(request, *args)

    def _switch_on(self):
        self._post(admin_views.admin_toggle_test_mode, SUPER, enable='1')

    def test_only_a_super_admin_can_switch_it_on(self):
        with self.assertRaises(Http404):
            self._post(admin_views.admin_toggle_test_mode, STAFF, enable='1')
        self.assertFalse(admin_views._test_mode_until())
        self._switch_on()
        self.assertGreater(admin_views._test_mode_until(), time.time() + 3600)

    def test_tools_need_the_switch_and_a_super_admin(self):
        with self.assertRaises(Http404):
            self._post(admin_views.admin_test_add_referrals, SUPER, self.participant.pk, count='1')
        self._switch_on()
        with self.assertRaises(Http404):
            self._post(admin_views.admin_test_add_referrals, STAFF, self.participant.pk, count='1')
        self._post(admin_views.admin_test_add_referrals, SUPER, self.participant.pk, count='1')
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.paid_count, 1)

    def test_switch_turns_itself_off(self):
        SiteSetting.set_value(admin_views.TEST_MODE_SETTING, str(int(time.time()) - 5), 'event')
        with self.assertRaises(Http404):
            self._post(admin_views.admin_test_add_referrals, SUPER, self.participant.pk, count='1')

    def test_test_referrals_never_get_an_invoice_or_reach_the_directory(self):
        self._switch_on()
        self._post(admin_views.admin_test_add_referrals, SUPER, self.participant.pk, count='3')
        subs = list(AgentSubscription.objects.filter(razorpay_payment_id__startswith='pay_TESTREF'))
        self.assertEqual(len(subs), 3)
        with patch('apps.agents.services.brevo.email_service') as mail:
            for sub in subs:
                self.assertIsNone(invoice_service.generate_from_subscription(sub.agent, sub))
                self.assertIsNone(fulfill_invoice_and_welcome(sub.agent, sub))
            found = retry_missing_invoices(days=2, min_age_minutes=0, apply=True)
        self.assertEqual(found, 0)
        self.assertEqual(Invoice.objects.count(), 0)
        mail.send_welcome.assert_not_called()
        fakes = Agent.objects.filter(email__endswith='@paldi-test.invalid')
        self.assertEqual(set(fakes.values_list('status', flat=True)), {'incomplete'})
        self.assertFalse(listed_agents_queryset().filter(email__endswith='@paldi-test.invalid').exists())

    def test_remove_withdraws_test_unlocked_claims(self):
        self._switch_on()
        self._post(admin_views.admin_test_add_referrals, SUPER, self.participant.pk, count='5')
        cp = ChampionshipParticipant.objects.get(agent=self.challenger)
        self.assertTrue(ChampionshipRewardClaim.objects.filter(participant=cp, reward_slab__threshold=5).exists())
        self._post(admin_views.admin_test_remove_referrals, SUPER, self.participant.pk)
        cp.refresh_from_db()
        self.assertEqual(cp.qualifying_referrals_count, 0)
        self.assertFalse(ChampionshipRewardClaim.objects.filter(participant=cp).exists())

    def test_real_paid_subscription_is_still_invoiced(self):
        real = Agent.objects.create(fullname='Real', email='real.payer@example.com', mobile='9000001502',
                                    status='pending_approval', plan_type='starter')
        sub = AgentSubscription.objects.create(agent=real, selected_plan="Starter's Plan", registration_amount='2359.00',
                                               payment_status='completed', status='active',
                                               razorpay_order_id='order_REALPAY00000001',
                                               razorpay_payment_id='pay_REALPAY000000001')
        from apps.agents.services.test_markers import is_test_subscription
        self.assertFalse(is_test_subscription(sub))
