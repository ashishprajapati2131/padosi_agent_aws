"""Audit phase 4: CH9 (public leaderboard cache / no referral contacts) and
CH11 (payment captured while the referrer is blocked counts after Restore)."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase

from apps.agents.models import Agent, AgentSubscription
from apps.event_referral.models import (
    EventReferral,
    EventReferralCampaign,
    EventReferralParticipant,
)
from apps.event_referral.services.participant_service import admin_restore_participant
from apps.event_referral.services.public_leaderboard import (
    get_public_leaderboard_payload,
)
from apps.event_referral.services.qualification_service import (
    qualify_event_referral,
    register_referred_agent,
)


class PublicLeaderboardCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_view_builds_rows_once_per_window(self):
        with patch(
            "apps.event_referral.views.public_leaderboard.get_public_leaderboard_payload",
            wraps=get_public_leaderboard_payload,
        ) as built:
            self.assertEqual(Client().get("/48HR/leaderboard/").status_code, 200)
            self.assertEqual(Client().get("/48HR/leaderboard/").status_code, 200)
        self.assertEqual(built.call_count, 1)

    def test_rows_carry_no_referred_contacts(self):
        campaign = EventReferralCampaign.get_current()
        host = Agent.objects.create(
            fullname="Host",
            email="host4@example.com",
            mobile="9000004001",
            status="event_challenge",
        )
        p = EventReferralParticipant.create_for_agent(host, campaign)
        friend = Agent.objects.create(
            fullname="Friend", email="friend4@example.com", mobile="9000004002"
        )
        EventReferral.objects.create(
            participant=p,
            referred_agent=friend,
            state=EventReferral.STATE_PAID,
            counts=True,
            registered_at=p.registered_at,
            snapshot_mobile="9000004002",
            snapshot_email="friend4@example.com",
        )
        resp = Client().get("/48HR/leaderboard/")
        self.assertNotContains(resp, "9000004002")
        self.assertNotContains(resp, "friend4@example.com")
        for row in resp.context["leaders"]:
            self.assertNotIn("referrals", row)


class BlockedReferrerPaymentTests(TestCase):
    def setUp(self):
        EventReferralCampaign.objects.all().delete()
        campaign = EventReferralCampaign.objects.create(
            is_enabled=True, required_paid_referrals=5, window_hours=48
        )
        self.referrer = Agent.objects.create(
            fullname="Ref",
            email="ref4@example.com",
            mobile="9000004101",
            status="event_challenge",
            plan_type="",
        )
        self.participant = EventReferralParticipant.create_for_agent(
            self.referrer, campaign
        )
        self.friend = Agent.objects.create(
            fullname="Pal",
            email="pal4@example.com",
            mobile="9000004102",
            status="pending_approval",
            plan_type="starter",
            referred_by_code=self.participant.referral_code,
        )
        register_referred_agent(self.friend)

    def test_paid_while_blocked_counts_after_restore(self):
        EventReferralParticipant.objects.filter(pk=self.participant.pk).update(
            status=EventReferralParticipant.STATUS_BLOCKED, blocked_by_admin=True
        )
        sub = AgentSubscription.objects.create(
            agent=self.friend,
            selected_plan="Starter's Plan",
            registration_amount=100,
            payment_status="completed",
            status="active",
            razorpay_order_id="order_PHASE4000000001",
            razorpay_payment_id="pay_PHASE40000000001",
        )
        qualify_event_referral(self.friend, sub)

        row = EventReferral.objects.get(referred_agent=self.friend)
        self.assertEqual((row.state, row.counts), (EventReferral.STATE_PAID, False))
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.paid_count, 0)

        restored = admin_restore_participant(self.participant)
        self.assertEqual(restored.status, EventReferralParticipant.STATUS_ACTIVE)
        self.assertEqual(restored.paid_count, 1)
        row.refresh_from_db()
        self.assertTrue(row.counts)
