"""Test helper: the default campaign has fixed 2026 dates, so tests move its window around today."""
import datetime

from apps.referral_championship.models import ChampionshipCampaign


def live_campaign():
    campaign = ChampionshipCampaign.get_current()
    now = datetime.datetime.now()
    campaign.start_date = now - datetime.timedelta(days=30)
    campaign.end_date = now + datetime.timedelta(days=30)
    campaign.save(update_fields=['start_date', 'end_date'])
    return campaign
