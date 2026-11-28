"""LIAFI event WhatsApp flow: entry, language, registration, profile menu, activation message, preview."""

import json
import unittest
from unittest.mock import MagicMock, patch

from django.test import RequestFactory

from apps.wa_agent_bot.models import WaBotSession
from apps.wa_agent_bot.services import flow_switches, liafi_flow
from apps.wa_agent_bot.services.state_machine import process_message


def _settings(values):
    return patch(
        "apps.home.models.site_setting.SiteSetting.get_value",
        side_effect=lambda key, default=None: values.get(key, default),
    )


class LiafiFlowTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.session.phone_number = "919876543210"
        self.session.state = WaBotSession.STATE_WELCOME
        self.session.registration_data = {}
        self.session.session_context = {}
        self.session.is_registered = False
        self.session.is_logged_in = False
        self.session.agent = None
        self.session.agent_id = None
        self.values = {}
        p = _settings(self.values)
        p.start()
        self.addCleanup(p.stop)
        app = patch.object(
            liafi_flow, "app_link", return_value="https://play.example/app"
        )
        app.start()
        self.addCleanup(app.stop)

    def say(self, text):
        return process_message(self.session, text)

    def test_keyword_starts_flow_even_with_event_mode_off(self):
        reply = self.say("LIAFI")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)
        self.assertIn("LIAFI General Council Meeting", reply)
        self.assertIn("1️⃣ 🚀 Register Now", reply)

    @patch("apps.agents.models.Agent.objects")
    def test_hi_goes_to_normal_registration_unless_event_mode(self, _agents):
        self.say("hi")
        self.assertEqual(self.session.state, WaBotSession.STATE_ASK_FULLNAME)

        self.session.state = WaBotSession.STATE_WELCOME
        self.values[flow_switches.LIAFI_EVENT_MODE] = "True"
        self.say("hi")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)

    @patch("apps.wa_agent_bot.services.payment_service.create_plan_payment_link")
    @patch("apps.agents.models.Agent.objects")
    def test_gujarati_registration_to_profile_menu(self, agents, create_link):
        agents.filter.return_value.exclude.return_value.exists.return_value = False
        agent = MagicMock(
            fullname="Ramesh Patel",
            registration_draft={},
            state_code="ap",
            agent_slug="ramesh-patel",
        )
        create_link.return_value = {
            "success": True,
            "agent": agent,
            "payment_link": "https://rzp.io/l/abc",
        }

        def fake_create(session, plan_key):
            session.registration_data["payment_link"] = "https://rzp.io/l/abc"
            return create_link.return_value

        create_link.side_effect = fake_create

        self.say("LIAFI")
        self.assertIn("Choose your preferred language", self.say("2"))
        reply = self.say("3")  # ગુજરાતી
        self.assertIn("ડિજિટલ ઓળખ", reply)
        self.assertIn("પૂરું નામ", reply)

        self.assertIn("ઈમેલ", self.say("Ramesh Patel"))
        self.assertIn("⚠️", self.say("not-an-email"))
        self.assertIn("બ્રાન્ચ કોડ", self.say("ramesh@example.com"))

        reply = self.say("VJA-01")
        create_link.assert_called_once()
        self.assertEqual(create_link.call_args[0][1], "starter")
        self.assertIn("અભિનંદન Ramesh Patel", reply)
        self.assertIn("/ap/ramesh-patel/", reply)
        self.assertIn("પ્રોફાઇલ એક્ટિવ કરો", reply)
        self.assertEqual(
            agent.registration_draft["liafi"],
            {"branch_code": "VJA-01", "language": "gu"},
        )
        self.assertEqual(self.session.registration_data["mobile"], "9876543210")

        self.assertIn("https://rzp.io/l/abc", self.say("1"))
        self.assertIn("https://play.example/app", self.say("2"))
        # No group link set yet: option 3 falls back to the contact numbers.
        self.assertIn("PadosiAgent સેલ્સ", self.say("3"))
        self.values[liafi_flow.SETTING_GROUP_LINK] = "https://chat.whatsapp.com/xyz"
        self.assertIn("https://chat.whatsapp.com/xyz", self.say("3"))

    @patch("apps.agents.models.Agent.objects")
    def test_email_already_used_is_refused(self, agents):
        agents.filter.return_value.exclude.return_value.exists.return_value = True
        self.say("LIAFI")
        self.say("1")
        self.say("Ramesh Patel")
        self.assertIn("already registered", self.say("taken@example.com"))
        self.assertEqual(self.session.session_context["liafi_step"], "email")

    def test_liafi_switched_off_ignores_keyword_and_event_mode(self):
        self.values[flow_switches.LIAFI] = "False"
        self.values[flow_switches.LIAFI_EVENT_MODE] = "True"
        self.values[flow_switches.REGISTRATION] = "False"
        reply = self.say("LIAFI")
        self.assertEqual(self.session.state, WaBotSession.STATE_WELCOME)
        self.assertIn("paused", reply)
        self.assertIn("+91 9898555837", reply)

    def test_registration_off_points_new_chats_to_liafi(self):
        self.values[flow_switches.REGISTRATION] = False
        reply = self.say("hi")
        self.assertEqual(self.session.state, WaBotSession.STATE_WELCOME)
        self.assertIn("Type *LIAFI*", reply)
        self.say("LIAFI")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)

    def test_flow_already_started_can_finish_after_switch_off(self):
        self.say("LIAFI")
        self.values[flow_switches.LIAFI] = False
        self.assertIn("Full Name", self.say("1"))

    def test_liafi_restarts_from_an_unfinished_normal_registration(self):
        self.session.state = WaBotSession.STATE_AWAITING_PAYMENT
        self.session.registration_data = {"fullname": "Old", "payment_link": "https://rzp.io/old"}
        reply = self.say("LIAFI")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)
        self.assertIn("LIAFI General Council Meeting", reply)
        self.assertNotIn("payment_link", self.session.registration_data)

    def test_registered_agent_is_not_pulled_into_liafi(self):
        self.session.is_registered = True
        self.session.agent = MagicMock()
        self.session.state = WaBotSession.STATE_LOGGED_IN
        with patch("apps.wa_agent_bot.services.state_machine._handle_logged_in", return_value="menu"):
            self.assertEqual(self.say("LIAFI"), "menu")
        self.assertEqual(self.session.state, WaBotSession.STATE_LOGGED_IN)

    def test_cancel_leaves_the_flow(self):
        self.say("LIAFI")
        self.say("cancel")
        self.assertEqual(self.session.state, WaBotSession.STATE_WELCOME)

    def test_contact_numbers_default_to_padosi_lines_and_hub_overrides(self):
        self.assertEqual(liafi_flow.contact_numbers(), ("+91 9898555837", "+91 9898555437"))
        self.values[liafi_flow.SETTING_SUPPORT] = "+91 90000 22222"
        self.assertEqual(liafi_flow.contact_numbers(), ("+91 9898555837", "+91 90000 22222"))


class LiafiActivationMessageTests(unittest.TestCase):
    def setUp(self):
        self.values = {}
        p = _settings(self.values)
        p.start()
        self.addCleanup(p.stop)
        self.agent = MagicMock(
            fullname="Ramesh Patel", state_code="ap", agent_slug="ramesh-patel"
        )

    def test_not_sent_for_normal_bot_signups(self):
        session = MagicMock(registration_data={"fullname": "X"})
        self.assertIsNone(liafi_flow.activated_message(session, self.agent))

    @patch.object(liafi_flow, "app_link", return_value="https://play.example/app")
    def test_steps_renumber_when_group_link_missing(self, _app):
        session = MagicMock(registration_data={"liafi": {"language": "hi"}})
        msg = liafi_flow.activated_message(session, self.agent)
        self.assertIn("बधाई हो Ramesh Patel", msg)
        self.assertIn("स्टेप 1:* PadosiAgent ऐप", msg)
        self.assertIn("स्टेप 2:* अपनी डिजिटल प्रोफाइल", msg)
        self.assertNotIn("कॉन्टेस्ट ग्रुप", msg)

        self.values[liafi_flow.SETTING_GROUP_LINK] = "https://chat.whatsapp.com/xyz"
        msg = liafi_flow.activated_message(session, self.agent)
        self.assertIn("स्टेप 2:* रजिस्ट्रेशन", msg)
        self.assertIn("स्टेप 3:*", msg)


class LiafiTranslationTests(unittest.TestCase):
    def test_every_language_has_every_key_and_no_stray_placeholders(self):
        keys = set(liafi_flow.TEXT["en"])
        allowed = {"{name}", "{link}", "{url}", "{sales}", "{support}", "{n}"}
        import re

        for lang, _ in liafi_flow.LANGUAGES:
            self.assertEqual(set(liafi_flow.TEXT[lang]), keys, lang)
            found = set(
                re.findall(
                    r"\{[a-z]+\}", json.dumps(liafi_flow.TEXT[lang], ensure_ascii=False)
                )
            )
            self.assertTrue(found <= allowed, (lang, found - allowed))


class LiafiProfilePreviewTests(unittest.TestCase):
    def _agent(self, **kw):
        defaults = dict(
            status="pending_payment",
            registration_draft={"liafi": {}},
            is_account_active=True,
            is_blacklisted=False,
        )
        defaults.update(kw)
        return MagicMock(**defaults)

    def test_only_unpaid_liafi_agents_get_the_preview(self):
        from apps.agents.views.qr import _liafi_profile_preview

        self.assertTrue(_liafi_profile_preview(self._agent()))
        self.assertFalse(
            _liafi_profile_preview(
                self._agent(registration_draft={"source": "whatsapp_bot"})
            )
        )
        self.assertFalse(_liafi_profile_preview(self._agent(status="suspended")))
        self.assertFalse(_liafi_profile_preview(self._agent(is_account_active=False)))
        self.assertFalse(_liafi_profile_preview(self._agent(is_blacklisted=True)))


class LiafiHubSaveTests(unittest.TestCase):
    def _post(self, body):
        from apps.admin_panel.views import wa_bot_admin

        request = RequestFactory().post(
            "/admin/whatsapp/save-liafi/",
            data=json.dumps(body),
            content_type="application/json",
        )
        with (
            patch.object(wa_bot_admin, "_get_admin_from_session", return_value=1),
            patch.object(wa_bot_admin.SiteSetting, "set_value") as set_value,
            patch.object(wa_bot_admin, "_log_admin_action"),
        ):
            response = wa_bot_admin.wa_bot_save_liafi(request)
        return json.loads(response.content), set_value

    def test_saves_valid_settings(self):
        data, set_value = self._post(
            {
                "event_mode": True,
                "group_link": "https://chat.whatsapp.com/xyz",
                "app_link": "",
                "sales_number": "+91 98765 43210",
                "support_number": "",
            }
        )
        self.assertTrue(data["success"])
        saved = {c.args[0]: c.args[1] for c in set_value.call_args_list}
        self.assertEqual(saved[liafi_flow.SETTING_SALES], "+91 98765 43210")

    def test_rejects_non_https_links_and_bad_numbers(self):
        data, set_value = self._post({"group_link": "javascript:alert(1)"})
        self.assertFalse(data["success"])
        set_value.assert_not_called()
        data, _ = self._post({"sales_number": "call me"})
        self.assertFalse(data["success"])


class BotFlowToggleTests(unittest.TestCase):
    def _post(self, body):
        from apps.admin_panel.views import wa_bot_admin

        request = RequestFactory().post(
            "/admin/whatsapp/toggle-flow/", data=json.dumps(body), content_type="application/json"
        )
        with patch.object(wa_bot_admin, "_get_admin_from_session", return_value=1), patch(
            "apps.home.models.site_setting.SiteSetting.set_value"
        ) as set_value, patch.object(wa_bot_admin, "_log_admin_action"):
            response = wa_bot_admin.wa_bot_toggle_flow(request)
        return response.status_code, json.loads(response.content), set_value

    def test_switches_a_known_flow(self):
        status, data, set_value = self._post({"key": flow_switches.LIAFI, "enabled": False})
        self.assertEqual((status, data["success"]), (200, True))
        set_value.assert_any_call(flow_switches.LIAFI, False, group="whatsapp")
        set_value.assert_any_call(flow_switches.LIAFI_EVENT_MODE, False, group="whatsapp")

    def test_rejects_unknown_keys(self):
        status, data, set_value = self._post({"key": "wa_bot_openwa_api_key", "enabled": True})
        self.assertEqual(status, 400)
        set_value.assert_not_called()

    def test_defaults_when_never_saved(self):
        with _settings({}):
            states = {f["key"]: f["enabled"] for f in flow_switches.all_switches()}
        self.assertEqual(
            states,
            {flow_switches.REGISTRATION: True, flow_switches.LIAFI: True, flow_switches.LIAFI_EVENT_MODE: False},
        )


class LiafiStuckPaymentSessionTests(unittest.TestCase):
    """Live bug 2026-11-28: a number stuck at an old normal-registration payment link kept getting
    that link for LIAFI / Hi while the LIAFI switch was off and event mode was on."""

    def setUp(self):
        self.session = MagicMock()
        self.session.phone_number = "916352701839"
        self.session.state = WaBotSession.STATE_AWAITING_PAYMENT
        self.session.registration_data = {"payment_link": "https://rzp.io/rzp/OLD"}
        self.session.session_context = {}
        self.session.is_registered = False
        self.session.is_logged_in = False
        self.session.agent = None
        self.session.agent_id = None
        self.values = {flow_switches.REGISTRATION: False}
        p = _settings(self.values)
        p.start()
        self.addCleanup(p.stop)

    def test_liafi_keyword_with_punctuation_leaves_the_old_payment(self):
        reply = process_message(self.session, "LIAFI.")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)
        self.assertIn("LIAFI General Council Meeting", reply)

    def test_hi_in_event_mode_leaves_the_old_payment(self):
        self.values[flow_switches.LIAFI_EVENT_MODE] = True
        reply = process_message(self.session, "Hi")
        self.assertEqual(self.session.state, WaBotSession.STATE_LIAFI)
        self.assertNotIn("rzp.io", reply)

    def test_hi_without_event_mode_keeps_the_payment_reminder(self):
        with patch("apps.wa_agent_bot.services.state_machine._handle_awaiting_payment", return_value="PAY"):
            self.assertEqual(process_message(self.session, "Hi"), "PAY")

    def test_registered_agents_keep_their_account_flow(self):
        self.session.is_registered = True
        self.session.state = WaBotSession.STATE_LOGGED_IN
        self.session.agent = MagicMock()
        self.values[flow_switches.LIAFI_EVENT_MODE] = True
        with patch(
            "apps.wa_agent_bot.services.state_machine.process_post_login_message", return_value="MENU"
        ):
            self.assertEqual(process_message(self.session, "Hi"), "MENU")

    def test_keyword_is_a_whole_word(self):
        self.assertTrue(liafi_flow.wants_liafi("hi liafi!"))
        self.assertFalse(liafi_flow.wants_liafi("liafix"))


class FlowSwitchLinkTests(unittest.TestCase):
    def test_event_mode_on_turns_liafi_on_and_liafi_off_turns_event_mode_off(self):
        with patch("apps.home.models.site_setting.SiteSetting.set_value") as set_value:
            flow_switches.set_switch(flow_switches.LIAFI_EVENT_MODE, True)
            flow_switches.set_switch(flow_switches.LIAFI, False)
        calls = [c.args[:2] for c in set_value.call_args_list]
        self.assertEqual(
            calls,
            [
                (flow_switches.LIAFI_EVENT_MODE, True),
                (flow_switches.LIAFI, True),
                (flow_switches.LIAFI, False),
                (flow_switches.LIAFI_EVENT_MODE, False),
            ],
        )
