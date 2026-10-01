"""Audit 2026-10-01 F-38: referral-link clicks were counted read-modify-write
(lost updates under concurrent visits), and /join/<code>/ saved the whole
referral_codes row from a stale read, which could undo total_referrals."""
from datetime import datetime

from django.test import TestCase, override_settings

from apps.admin_panel.models.referral_code import ReferralCode
from apps.agents.models import Agent


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class ReferralClickCounterTests(TestCase):
    def setUp(self):
        agent = Agent.objects.create(fullname='Ref', email='clicks@example.com', mobile='9000000171')
        self.code = ReferralCode.objects.create(agent=agent, code='CLICK1234', clicks=0, total_referrals=0,
                                                created_at=datetime.now(), updated_at=datetime.now())

    def test_concurrent_stale_reads_count_every_click(self):
        from apps.agents.views.registration import _bump_clicks
        first = ReferralCode.objects.get(pk=self.code.pk)
        second = ReferralCode.objects.get(pk=self.code.pk)   # both requests read clicks=0
        _bump_clicks(first)
        _bump_clicks(second)
        self.assertEqual(ReferralCode.objects.get(pk=self.code.pk).clicks, 2)

    def test_click_leaves_other_counters_alone(self):
        from apps.agents.views.registration import _bump_clicks
        stale = ReferralCode.objects.get(pk=self.code.pk)
        ReferralCode.objects.filter(pk=self.code.pk).update(total_referrals=7)  # a conversion meanwhile
        _bump_clicks(stale)
        fresh = ReferralCode.objects.get(pk=self.code.pk)
        self.assertEqual((fresh.clicks, fresh.total_referrals), (1, 7))

    def test_join_link_counts_a_click(self):
        self.client.get('/join/CLICK1234/')
        self.assertEqual(ReferralCode.objects.get(pk=self.code.pk).clicks, 1)
        self.assertEqual(self.client.session.get('ref_code'), 'CLICK1234')
