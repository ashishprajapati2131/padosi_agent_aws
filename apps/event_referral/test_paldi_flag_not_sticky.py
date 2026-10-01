"""Audit 2026-10-01 F-17d: the Paldi page sets a session flag that turns step 1
into a free challenge signup. It stayed set on a shared stall device, so the
next person opening a referral or distributor signup page there was enrolled
in the challenge instead of the normal paid signup."""
from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings

from apps.event_referral.models import EventReferralCampaign

FLAG = 'event_referral_registration'


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost'])
class PaldiFlagNotStickyTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        EventReferralCampaign.objects.create(is_enabled=True, required_paid_referrals=2, window_hours=48)
        self.client.get('/48HR/')
        self.assertTrue(self.client.session.get(FLAG))   # the Paldi page still sets it

    def test_referral_page_clears_the_flag(self):
        self.client.get('/agent-registration/join/EV-NOSUCH1/')
        self.assertNotIn(FLAG, self.client.session)

    def test_distributor_onboarding_clears_the_flag(self):
        user = User.objects.create_user('dist.flag@example.com', 'dist.flag@example.com', 'pw')
        user.groups.add(Group.objects.get_or_create(name='distributor')[0])
        self.client.force_login(user)
        self.client.get('/distributor/agents/create/')
        self.assertNotIn(FLAG, self.client.session)
