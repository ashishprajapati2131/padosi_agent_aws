"""Ending a campaign must not crash get_current() or keep the campaign price (audit CH1/CH2)."""

import datetime

from django.test import TestCase

from apps.referral_championship.models import ChampionshipCampaign
from apps.referral_championship.testing import live_campaign


class CampaignLifecycleTests(TestCase):
    def test_ended_campaign_is_returned_not_reseeded(self):
        campaign = live_campaign()
        campaign.status = "ended"
        campaign.save(update_fields=["status"])

        current = ChampionshipCampaign.get_current()  # raised IntegrityError before

        self.assertEqual(current.pk, campaign.pk)
        self.assertEqual(ChampionshipCampaign.objects.count(), 1)

    def test_offer_open_only_while_live_and_before_end(self):
        campaign = live_campaign()
        self.assertTrue(campaign.offer_is_open())

        campaign.end_date = datetime.datetime.now() - datetime.timedelta(minutes=1)
        self.assertFalse(campaign.offer_is_open())

        campaign.end_date = datetime.datetime.now() + datetime.timedelta(days=1)
        campaign.status = "paused"
        self.assertFalse(campaign.offer_is_open())

    def test_empty_table_still_seeds_default(self):
        ChampionshipCampaign.objects.all().delete()
        self.assertEqual(ChampionshipCampaign.get_current().slug, "championship-2026")
