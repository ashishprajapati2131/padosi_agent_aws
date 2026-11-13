"""The bot must never reset the password of a login it did not create (audit WA1)."""
from django.contrib.auth.models import User
from django.test import TestCase

from apps.agents.models import Agent
from apps.wa_agent_bot.models import WaBotSession
from apps.wa_agent_bot.services.payment_service import (
    EmailAlreadyTaken,
    create_or_update_pending_agent,
)


def _reg(email, mobile="9876500001"):
    return {
        "email": email, "fullname": "Wa Tester", "mobile": mobile,
        "state": "Gujarat", "agent_pincode": "380015", "segments": ["health"],
    }


class BotTakeoverTests(TestCase):
    def test_existing_staff_login_keeps_its_password(self):
        staff = User.objects.create_user("boss@example.com", "boss@example.com", "Secret#123", is_staff=True)
        with self.assertRaises(EmailAlreadyTaken):
            create_or_update_pending_agent(_reg("boss@example.com"), "starter")
        staff.refresh_from_db()
        self.assertTrue(staff.check_password("Secret#123"))
        self.assertFalse(Agent.objects.filter(email="boss@example.com").exists())

    def test_someone_elses_pending_agent_is_not_hijacked(self):
        victim = Agent.objects.create(fullname="V", email="v@example.com", mobile="9000000001", status="pending_payment")
        with self.assertRaises(EmailAlreadyTaken):
            create_or_update_pending_agent(_reg("v@example.com", "9111111111"), "starter")
        victim.refresh_from_db()
        self.assertEqual(victim.mobile, "9000000001")

    def test_new_email_then_plan_change_by_same_session_works(self):
        agent, user, pw = create_or_update_pending_agent(_reg("new@example.com"), "starter")
        self.assertEqual(agent.status, "pending_payment")
        self.assertTrue(user.check_password(pw))
        again, user2, pw2 = create_or_update_pending_agent(
            _reg("new@example.com"), "professional", owner_agent=agent
        )
        self.assertEqual((again.pk, user2.pk), (agent.pk, user.pk))
        self.assertEqual(again.plan_type, "professional")

    def test_plan_step_sends_user_back_to_email_question(self):
        User.objects.create_user("taken@example.com", "taken@example.com", "x")
        session = WaBotSession.objects.create(
            phone_number="919876500002", state=WaBotSession.STATE_ASK_PLAN,
            registration_data=_reg("taken@example.com", "9876500002"),
        )
        from apps.wa_agent_bot.services.state_machine import process_message

        reply = process_message(session, "1")
        self.assertEqual(session.state, WaBotSession.STATE_ASK_EMAIL)
        self.assertIn("can't be used here", reply)
        self.assertNotIn("email", session.registration_data)
