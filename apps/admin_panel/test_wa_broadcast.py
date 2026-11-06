"""
WhatsApp broadcast: sheet parsing, recipient building, sending loop and the admin page.
Run: python manage.py test apps.admin_panel.test_wa_broadcast
"""

import io
import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase

from apps.admin_panel.views.wa_bot_admin import (
    wa_bot_broadcast,
    wa_bot_broadcast_action,
    wa_bot_broadcast_progress,
    wa_bot_broadcast_templates,
)
from apps.agents.models import Agent
from apps.wa_agent_bot.models import WaBotMessageLog, WaBroadcast, WaBroadcastRecipient
from apps.wa_agent_bot.services import broadcast


def _csv(text, name="list.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"))


def _xlsx(rows):
    from openpyxl import Workbook

    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("list.xlsx", buf.getvalue())


class PhoneAndSheetTests(TestCase):
    def test_phone10(self):
        self.assertEqual(broadcast.phone10("+91 98765-43210"), "9876543210")
        self.assertEqual(broadcast.phone10("919876543210"), "9876543210")
        self.assertEqual(broadcast.phone10(9876543210.0), "9876543210")
        self.assertEqual(broadcast.phone10("12345"), "")
        self.assertEqual(
            broadcast.phone10("1234567890"), ""
        )  # Indian mobiles start 6-9
        self.assertEqual(broadcast.phone10(None), "")

    def test_csv_with_headers(self):
        rows = broadcast.parse_sheet(
            _csv("Name,Mobile No\nRam,98765 43210\nBad,123\nSita,+918888888888\n")
        )
        self.assertEqual(rows, [("Ram", "9876543210"), ("Sita", "8888888888")])

    def test_csv_without_header_finds_phone_column(self):
        rows = broadcast.parse_sheet(_csv("Ram,9876543210\nSita,8888888888\n"))
        self.assertEqual([p for _, p in rows], ["9876543210", "8888888888"])

    def test_xlsx_numeric_cells(self):
        rows = broadcast.parse_sheet(
            _xlsx([["name", "whatsapp"], ["Ram", 9876543210], ["Sita", 8888888888.0]])
        )
        self.assertEqual(rows, [("Ram", "9876543210"), ("Sita", "8888888888")])

    def test_rejects_bad_files(self):
        with self.assertRaises(ValueError):
            broadcast.parse_sheet(_csv("a,b\nx,y\n"))
        with self.assertRaises(ValueError):
            broadcast.parse_sheet(_csv("9876543210", name="list.txt"))
        with self.assertRaises(ValueError):
            broadcast.parse_sheet(_csv(""))


class RecipientAndSendTests(TestCase):
    def setUp(self):
        self.a1 = Agent.objects.create(
            fullname="Ram Patel",
            email="ram@example.com",
            mobile="9876543210",
            status="active",
        )
        self.a2 = Agent.objects.create(
            fullname="Sita Shah",
            email="sita@example.com",
            mobile="8888888888",
            status="active",
        )

    def test_dedupes_and_links_sheet_agents(self):
        recips = broadcast.build_recipients(
            agents=[self.a1],
            sheet_rows=[
                ("", "9876543210"),
                ("", "8888888888"),
                ("Guest", "7777777777"),
            ],
            base="https://padosiagent.com",
        )
        self.assertEqual(
            [r["phone"] for r in recips], ["9876543210", "8888888888", "7777777777"]
        )
        self.assertTrue(recips[0]["link"].startswith("https://padosiagent.com/"))
        self.assertEqual(
            recips[1]["name"], "Sita Shah"
        )  # sheet number matched to an agent
        self.assertTrue(recips[1]["link"])
        self.assertEqual(recips[2]["link"], "")  # not an agent: no profile link

    def test_no_links_when_disabled(self):
        recips = broadcast.build_recipients(agents=[self.a1], add_link=False)
        self.assertEqual(recips[0]["link"], "")

    def test_render_text(self):
        self.assertEqual(broadcast.render_text("Hi {name}!", "Ram", ""), "Hi Ram!")
        self.assertEqual(
            broadcast.render_text("Hi", "", "https://x/"),
            "Hi\n\nYour profile: https://x/",
        )
        # {link} puts the link where the admin wants it, and only once.
        self.assertEqual(
            broadcast.render_text("Hi {name}\nSee {link} now", "Ram", "https://x/"),
            "Hi Ram\nSee https://x/ now",
        )
        self.assertEqual(broadcast.render_text("Hi\n{link}", "", ""), "Hi")
        self.assertEqual(broadcast.render_text("Hi\n\nYour profile: {link}\nBye", "", ""), "Hi\n\nBye")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message")
    def test_skips_numbers_already_sent(self, send):
        def fake_send(phone, text, category):
            WaBotMessageLog.objects.create(
                phone_number="91" + phone,
                direction=WaBotMessageLog.DIRECTION_OUT,
                category=category,
                status=WaBotMessageLog.STATUS_SENT,
                content=text,
            )
            return {"success": True}

        send.side_effect = fake_send
        recips = broadcast.build_recipients(agents=[self.a1, self.a2], add_link=False)

        first = broadcast.run_broadcast(recips, "Happy Diwali", 0, 0)
        again = broadcast.run_broadcast(recips, "Happy Diwali", 0, 0)
        self.assertEqual((first["sent"], first["skipped"]), (2, 0))
        self.assertEqual((again["sent"], again["skipped"]), (0, 2))
        self.assertEqual(send.call_count, 2)

    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": False, "error": "down"},
    )
    def test_failures_and_stop(self, send):
        recips = broadcast.build_recipients(agents=[self.a1, self.a2], add_link=False)
        stats = broadcast.run_broadcast(
            recips, "Hi", 0, 0, should_stop=lambda: send.call_count >= 1
        )
        self.assertEqual(stats["failed"], 1)
        self.assertTrue(stats["cancelled"])
        self.assertIn("down", stats["errors"][0])


CONNECTED = {"is_connected": True, "status": "ready"}
LOGGED_OUT = {"is_connected": False, "status": "qr_ready", "error": None}


class SavedBroadcastJobTests(TestCase):
    """The 'wa-broadcast' background job: pacing, pause on ban, alert email, auto-resume."""

    def setUp(self):
        self.recips = [
            {"phone": "9876543210", "name": "Ram", "link": ""},
            {"phone": "8888888888", "name": "Sita", "link": ""},
            {"phone": "7777777777", "name": "Guest", "link": ""},
        ]

    def _make(self, **kw):
        kw.setdefault("rate_count", 49)
        kw.setdefault("rate_hours", 4)
        kw.setdefault("alert_email", "boss@example.com")
        return broadcast.create_broadcast(self.recips, "Happy Diwali {name}", **kw)

    def _pending(self, b):
        return b.recipients.filter(status=WaBroadcastRecipient.STATUS_PENDING).count()

    def test_gap_uses_slower_of_rate_and_min_delay(self):
        b = self._make(rate_count=49, rate_hours=4, min_gap_seconds=60)
        self.assertAlmostEqual(b.gap_seconds, 4 * 3600 / 49)
        b.min_gap_seconds = 600
        self.assertEqual(b.gap_seconds, 600)

    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": True},
    )
    def test_sends_one_then_waits_for_the_gap(self, send):
        b = self._make()
        broadcast.process_broadcasts(max_seconds=5, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(send.call_count, 1)  # next one is ~5 min away, past this run
        self.assertEqual(send.call_args[0][1], "Happy Diwali Ram")
        self.assertGreater(b.next_send_at, datetime.now() + timedelta(minutes=3))
        self.assertEqual(self._pending(b), 2)

    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": True},
    )
    def test_finishes_when_everyone_is_sent(self, send):
        b = self._make(rate_count=1000, rate_hours=0.1, min_gap_seconds=5)
        for _ in range(4):
            WaBroadcast.objects.filter(pk=b.pk).update(next_send_at=datetime.now())
            broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(send.call_count, 3)
        self.assertEqual(b.status, WaBroadcast.STATUS_DONE)

    @patch("apps.agents.services.brevo.send_brevo_email")
    @patch(
        "apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status",
        return_value=LOGGED_OUT,
    )
    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": False, "error": "HTTP 401"},
    )
    def test_ban_pauses_emails_once_and_keeps_number_pending(self, send, status, email):
        b = self._make()
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_BLOCKED)
        self.assertEqual(self._pending(b), 3)  # nobody lost
        self.assertEqual(email.call_count, 1)
        self.assertEqual(email.call_args[0][0], "boss@example.com")

        # Still banned at the next check: no second email, still paused.
        WaBroadcast.objects.filter(pk=b.pk).update(next_check_at=datetime.now())
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_BLOCKED)
        self.assertEqual(email.call_count, 1)
        self.assertEqual(send.call_count, 1)

    @patch("apps.agents.services.brevo.send_brevo_email")
    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": True},
    )
    def test_resumes_by_itself_when_whatsapp_is_back(self, send, email):
        b = self._make()
        WaBroadcast.objects.filter(pk=b.pk).update(
            status=WaBroadcast.STATUS_BLOCKED,
            alert_sent=True,
            blocked_at=datetime.now() - timedelta(hours=24),
            next_check_at=datetime.now() - timedelta(seconds=1),
        )
        with patch(
            "apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status",
            return_value=CONNECTED,
        ):
            broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_RUNNING)
        self.assertEqual(send.call_count, 1)
        self.assertFalse(b.alert_sent)  # a later ban sends a fresh email

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message")
    def test_waits_until_recheck_time(self, send):
        b = self._make()
        WaBroadcast.objects.filter(pk=b.pk).update(
            status=WaBroadcast.STATUS_BLOCKED,
            next_check_at=datetime.now() + timedelta(minutes=10),
        )
        with patch(
            "apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status"
        ) as status:
            broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
            status.assert_not_called()
        send.assert_not_called()

    @patch("apps.agents.services.brevo.send_brevo_email")
    @patch(
        "apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status",
        return_value=CONNECTED,
    )
    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": False, "error": "rate-overlimit"},
    )
    def test_failures_while_connected_pause_after_streak(self, send, status, email):
        many = [{"phone": f"98000000{i:02d}", "name": "", "link": ""} for i in range(8)]
        b = broadcast.create_broadcast(
            many,
            "Hi",
            rate_count=1000,
            rate_hours=0.1,
            min_gap_seconds=5,
            alert_email="boss@example.com",
        )
        for _ in range(broadcast.FAIL_STREAK_LIMIT):
            WaBroadcast.objects.filter(pk=b.pk).update(next_send_at=datetime.now())
            broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_BLOCKED)
        self.assertGreater(b.next_check_at, datetime.now() + timedelta(minutes=50))
        self.assertEqual(email.call_count, 1)

    @patch(
        "apps.wa_agent_bot.services.broadcast.send_text_message",
        return_value={"success": True},
    )
    def test_cancel_stops_sending_and_queue_runs_in_order(self, send):
        first, second = self._make(), self._make()
        self.assertEqual(broadcast.cancel_broadcast(first.pk), 1)
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        first.refresh_from_db()
        self.assertEqual(first.status, WaBroadcast.STATUS_CANCELLED)
        self.assertEqual(self._pending(first), 3)
        self.assertEqual(self._pending(second), 2)

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message", return_value={"success": True})
    def test_second_sender_waits_for_the_lock(self, send):
        from django.core.cache import cache

        self._make()
        cache.set(broadcast.SEND_LOCK, 1, 60)  # another process is sending
        try:
            self.assertFalse(broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None, source="page"))
        finally:
            cache.delete(broadcast.SEND_LOCK)
        send.assert_not_called()
        self.assertTrue(broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None, source="page"))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(broadcast.sender_status()["last_source"], "page")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message", return_value={"success": True})
    def test_open_page_sends_the_due_message(self, send):
        b = self._make()
        factory = RequestFactory()
        req = factory.post("/admin/whatsapp/broadcast/progress/")
        req.session = {"admin_id": 1}
        req.user = AnonymousUser()
        with patch("apps.admin_panel.views.wa_bot_admin._get_admin_from_session", return_value=1):
            resp = wa_bot_broadcast_progress(req)
            get_req = factory.get("/admin/whatsapp/broadcast/progress/")
            get_req.session, get_req.user = {"admin_id": 1}, AnonymousUser()
            self.assertEqual(wa_bot_broadcast_progress(get_req).status_code, 405)
        data = json.loads(resp.content)
        self.assertTrue(data["success"])
        self.assertEqual(send.call_count, 1)  # the first message goes out on the first check
        self.assertEqual(data["broadcasts"][0]["sent"], 1)
        self.assertIn("jobs_enabled", data["sender"])
        self.assertEqual(b.recipients.filter(status="sent").count(), 1)

    def test_job_is_registered(self):
        from apps.agents.services.background_jobs import JOBS

        self.assertIn("wa-broadcast", [name for name, _, _ in JOBS])

    def test_openwa_keepalive_pings_every_5_minutes(self):
        from apps.agents.services import background_jobs

        self.assertIn(
            ("openwa-keepalive", 300), [(n, i) for n, i, _ in background_jobs.JOBS]
        )
        with (
            patch(
                "apps.wa_agent_bot.services.openwa_admin_service.get_openwa_session_status",
                return_value={"online": False, "status": "offline", "error": "timeout"},
            ) as status,
            self.assertLogs("apps.agents.services.background_jobs", level="WARNING"),
        ):
            background_jobs._openwa_keepalive_job()
        status.assert_called_once()


class BroadcastViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.agent = Agent.objects.create(
            fullname="Ram Patel",
            email="ram@example.com",
            mobile="9876543210",
            status="active",
        )
        self.inactive = Agent.objects.create(
            fullname="Old",
            email="old@example.com",
            mobile="9999999999",
            status="incomplete",
        )

    def _req(self, method="get", data=None):
        req = getattr(self.factory, method)("/admin/whatsapp/broadcast/", data or {})
        req.session = {"admin_id": 1, "admin_name": "Boss"}
        req.user = AnonymousUser()
        setattr(req, "_messages", FallbackStorage(req))
        return req

    def _call(self, view, *args):
        with patch(
            "apps.admin_panel.views.wa_bot_admin._get_admin_from_session",
            return_value=1,
        ):
            return view(*args)

    def test_requires_admin(self):
        with patch(
            "apps.admin_panel.views.wa_bot_admin._get_admin_from_session",
            return_value=None,
        ):
            resp = wa_bot_broadcast(self._req())
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(WaBroadcast.objects.exists())

    def test_page_lists_only_active_agents(self):
        resp = self._call(wa_bot_broadcast, self._req())
        self.assertContains(resp, "Ram Patel")
        self.assertNotContains(resp, "9999999999")

    def test_filters_get_plan_state_and_city(self):
        from apps.home.models.pincode import Pincode

        Pincode.objects.create(
            pincode="380001",
            office_name="Ahmedabad GPO",
            district="Ahmedabad",
            state="GUJARAT",
            latitude=0,
            longitude=0,
        )
        Agent.objects.filter(pk=self.agent.pk).update(
            plan_type="professional", agent_pincode="380001"
        )
        resp = self._call(wa_bot_broadcast, self._req())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp, 'data-plan="Professional" data-state="Gujarat" data-city="Ahmedabad"'
        )
        self.assertContains(resp, "<option>Ahmedabad</option>", html=False)

    def test_post_saves_broadcast_with_selected_active_agents_and_pace(self):
        data = {
            "message": "Happy Diwali",
            "add_link": "1",
            "agent_ids": [self.agent.id, self.inactive.id, "x"],
            "rate_count": "49",
            "rate_hours": "4",
            "min_gap_seconds": "90",
            "alert_email": "me@example.com",
            "send_card": "1",
        }
        resp = self._call(wa_bot_broadcast, self._req("post", data))
        self.assertEqual(resp.status_code, 302)
        b = WaBroadcast.objects.get()
        self.assertEqual(
            list(b.recipients.values_list("phone", flat=True)), ["9876543210"]
        )
        self.assertTrue(b.recipients.get().link)
        self.assertEqual((b.rate_count, b.rate_hours, b.min_gap_seconds), (49, 4.0, 90))
        self.assertEqual((b.alert_email, b.created_by), ("me@example.com", "Boss"))
        self.assertTrue(b.send_card)
        self.assertIn("/og-image/", b.recipients.get().image_url)

    def test_post_clamps_unsafe_speed(self):
        data = {
            "message": "Hi",
            "agent_ids": [self.agent.id],
            "rate_count": "99999",
            "rate_hours": "0",
            "min_gap_seconds": "0",
        }
        self._call(wa_bot_broadcast, self._req("post", data))
        b = WaBroadcast.objects.get()
        self.assertEqual(
            (b.rate_count, b.rate_hours, b.min_gap_seconds), (1000, 0.1, 5)
        )

    def test_post_rejects_bad_input(self):
        self._call(wa_bot_broadcast, self._req("post", {"message": "Hi"}))
        self._call(
            wa_bot_broadcast,
            self._req("post", {"message": "", "agent_ids": [self.agent.id]}),
        )
        self._call(
            wa_bot_broadcast,
            self._req(
                "post",
                {"message": "Hi", "agent_ids": [self.agent.id], "alert_email": "nope"},
            ),
        )
        self.assertFalse(WaBroadcast.objects.exists())

    def test_stop_and_try_now_actions(self):
        b = broadcast.create_broadcast(
            [{"phone": "9876543210", "name": "", "link": ""}], "Hi"
        )
        WaBroadcast.objects.filter(pk=b.pk).update(status=WaBroadcast.STATUS_BLOCKED)
        self._call(
            wa_bot_broadcast_action, self._req("post", {"action": "resume"}), b.pk
        )
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_RUNNING)
        self._call(
            wa_bot_broadcast_action, self._req("post", {"action": "cancel"}), b.pk
        )
        b.refresh_from_db()
        self.assertEqual(b.status, WaBroadcast.STATUS_CANCELLED)

    def test_page_has_each_agents_profile_link_for_preview(self):
        resp = self._call(wa_bot_broadcast, self._req())
        self.assertContains(
            resp,
            f'data-name="Ram Patel" data-link="{broadcast.profile_link(self.agent)}"',
        )
        self.assertContains(resp, "Diwali 2026")  # default pre-drafted message


class LinkPreviewTests(TestCase):
    """OpenWA >= 0.14 (Baileys) only builds the profile card when asked with linkPreview."""

    CFG = {"base_url": "https://wa.example.com", "session_id": "s1", "api_key": "k"}

    def _resp(self, code, body="{}"):
        from unittest.mock import MagicMock

        r = MagicMock(status_code=code, text=body)
        r.json.return_value = {}
        return r

    def test_asks_for_preview_only_when_text_has_a_link(self):
        from apps.wa_agent_bot.services import message_sender

        with patch.object(message_sender, "_get_config", return_value=self.CFG), \
                patch.object(message_sender.requests, "post", return_value=self._resp(201)) as post:
            message_sender._send("9876543210", "Hi\n\nYour profile: https://padosiagent.com/gj/ram/")
            message_sender._send("9876543210", "Hi, no link here")
        self.assertIs(post.call_args_list[0].kwargs["json"]["linkPreview"], True)
        self.assertNotIn("linkPreview", post.call_args_list[1].kwargs["json"])

    def test_older_openwa_that_rejects_the_field_still_gets_the_message(self):
        from apps.wa_agent_bot.services import message_sender

        with patch.object(message_sender, "_get_config", return_value=self.CFG), \
                patch.object(message_sender.requests, "post",
                             side_effect=[self._resp(400, "property linkPreview should not exist"), self._resp(201)]) as post:
            result = message_sender._send("9876543210", "See https://padosiagent.com/gj/ram/")
        self.assertTrue(result["success"])
        self.assertEqual(post.call_count, 2)
        self.assertNotIn("linkPreview", post.call_args_list[1].kwargs["json"])


class RepeatBroadcastTests(TestCase):
    """Each new broadcast reaches everyone; only a resend inside the same broadcast is skipped."""

    RECIPS = [{"phone": "9876543210", "name": "Ram", "link": "", "image": ""}]

    def _log(self, text, when):
        log = WaBotMessageLog.objects.create(phone_number="919876543210", direction=WaBotMessageLog.DIRECTION_OUT,
                                             category="broadcast", status=WaBotMessageLog.STATUS_SENT, content=text)
        WaBotMessageLog.objects.filter(pk=log.pk).update(created_at=when)

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message", return_value={"success": True})
    def test_new_broadcast_resends_same_text_to_same_person(self, send):
        self._log("Happy Diwali Ram", datetime.now() - timedelta(hours=1))  # an earlier broadcast
        b = broadcast.create_broadcast(self.RECIPS, "Happy Diwali {name}")
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        send.assert_called_once()
        self.assertEqual(b.recipients.get().status, "sent")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message")
    def test_resend_inside_the_same_broadcast_is_skipped(self, send):
        b = broadcast.create_broadcast(self.RECIPS, "Happy Diwali {name}")
        self._log("Happy Diwali Ram", datetime.now())  # sent, then the worker died before saving
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        send.assert_not_called()
        self.assertEqual(b.recipients.get().status, "skipped")


class CardPhotoTests(TestCase):
    """Broadcasts send the agent's profile card as a photo, so it shows whatever OpenWA does with link previews."""

    def setUp(self):
        self.agent = Agent.objects.create(fullname="Ram Patel", email="ram@example.com", mobile="9876543210", status="active")

    def _broadcast(self, text="Happy Diwali {name}", **kw):
        recips = broadcast.build_recipients(agents=[self.agent], base="https://padosiagent.com")
        return broadcast.create_broadcast(recips, text, rate_count=1000, rate_hours=0.1, min_gap_seconds=5, **kw)

    def test_recipient_gets_the_agents_card_image(self):
        (r,) = broadcast.build_recipients(agents=[self.agent], base="https://padosiagent.com")
        self.assertTrue(r["image"].startswith(f"https://padosiagent.com/og-image/{self.agent.id}/preview.jpg?v="))
        (no_link,) = broadcast.build_recipients(agents=[self.agent], add_link=False)
        self.assertEqual(no_link["image"], "")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message")
    @patch("apps.wa_agent_bot.services.broadcast.send_image_message", return_value={"success": True})
    def test_sends_card_photo_with_text_as_caption(self, image, text):
        b = self._broadcast()
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        phone, url, caption = image.call_args[0]
        self.assertEqual(phone, "9876543210")
        self.assertIn(f"/og-image/{self.agent.id}/preview.jpg", url)
        self.assertTrue(caption.startswith("Happy Diwali Ram Patel"))
        self.assertIn("Your profile: https://padosiagent.com/", caption)
        text.assert_not_called()
        self.assertEqual(b.recipients.get().status, "sent")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message", return_value={"success": True})
    @patch("apps.wa_agent_bot.services.broadcast.send_image_message", return_value={"success": False, "error": "HTTP 404"})
    def test_falls_back_to_text_when_photo_fails(self, image, text):
        b = self._broadcast()
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        image.assert_called_once()
        text.assert_called_once()
        self.assertEqual(b.recipients.get().status, "sent")

    @patch("apps.wa_agent_bot.services.broadcast.send_text_message", return_value={"success": True})
    @patch("apps.wa_agent_bot.services.broadcast.send_image_message")
    def test_text_only_when_turned_off_or_too_long(self, image, text):
        self._broadcast(send_card=False)
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        WaBroadcast.objects.all().delete()
        self._broadcast(text="x" * 1100)
        broadcast.process_broadcasts(max_seconds=1, sleep=lambda s: None)
        image.assert_not_called()
        self.assertEqual(text.call_count, 2)

    def test_send_image_payload(self):
        from unittest.mock import MagicMock
        from apps.wa_agent_bot.services import message_sender

        cfg = {"base_url": "https://wa.example.com", "session_id": "s1", "api_key": "k"}
        ok = MagicMock(status_code=201, text="{}")
        ok.json.return_value = {}
        with patch.object(message_sender, "_get_config", return_value=cfg), \
                patch.object(message_sender.requests, "post", return_value=ok) as post:
            result = message_sender.send_image_message("9876543210", "https://padosiagent.com/og-image/1/preview.jpg", "Hi", category="broadcast")
        self.assertTrue(result["success"])
        self.assertTrue(post.call_args[0][0].endswith("/api/sessions/s1/messages/send-image"))
        self.assertEqual(post.call_args.kwargs["json"],
                         {"chatId": "919876543210@c.us", "url": "https://padosiagent.com/og-image/1/preview.jpg", "caption": "Hi"})
        self.assertTrue(WaBotMessageLog.objects.filter(category="broadcast", content="Hi", status="sent").exists())


class SavedMessageTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _post(self, data, admin=1):
        req = self.factory.post("/admin/whatsapp/broadcast/templates/", data)
        req.session = {"admin_id": admin}
        req.user = AnonymousUser()
        with patch(
            "apps.admin_panel.views.wa_bot_admin._get_admin_from_session",
            return_value=admin,
        ):
            return wa_bot_broadcast_templates(req)

    def test_default_has_the_diwali_message_with_link(self):
        (tpl,) = broadcast.get_templates()
        self.assertEqual(tpl["name"], "Diwali 2026")
        self.assertIn("#PadosiWaliDiwali", tpl["text"])
        self.assertIn("{link}", tpl["text"])

    def test_save_replace_and_delete(self):
        broadcast.save_template("New Year", "Happy new year {name}")
        broadcast.save_template("New Year", "Edited text")
        names = [t["name"] for t in broadcast.get_templates()]
        self.assertEqual(names, ["Diwali 2026", "New Year"])
        self.assertEqual(broadcast.get_templates()[1]["text"], "Edited text")
        broadcast.delete_template("Diwali 2026")
        self.assertEqual([t["name"] for t in broadcast.get_templates()], ["New Year"])
        broadcast.delete_template("New Year")
        self.assertEqual(
            broadcast.get_templates(), []
        )  # deleting all does not bring the default back

    def test_save_validation(self):
        for name, text in [("", "x"), ("n", ""), ("n", "x" * 4001)]:
            with self.assertRaises(ValueError):
                broadcast.save_template(name, text)

    def test_endpoint(self):
        resp = self._post({"op": "save", "name": "Offer", "text": "50% off"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            "Offer", [t["name"] for t in json.loads(resp.content)["templates"]]
        )
        resp = self._post({"op": "save", "name": "", "text": "x"})
        self.assertFalse(json.loads(resp.content)["success"])
        resp = self._post({"op": "delete", "name": "Offer"})
        self.assertNotIn(
            "Offer", [t["name"] for t in json.loads(resp.content)["templates"]]
        )
        self.assertEqual(
            self._post(
                {"op": "save", "name": "x", "text": "y"}, admin=None
            ).status_code,
            401,
        )
