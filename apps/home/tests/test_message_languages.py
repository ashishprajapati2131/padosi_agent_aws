import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.home.services import message_languages as ml


class MessageLanguagesServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_has_english_plus_22_scheduled_languages(self):
        self.assertEqual(len(ml.LANGUAGES), 23)
        self.assertEqual(ml.LANGUAGES[0][0], "en")
        self.assertEqual(len(ml.LANGUAGE_CODES), 23)

    def test_pick_and_clean(self):
        self.assertEqual(ml.pick("Hi", {"gu": "કેમ છો"}, "gu"), "કેમ છો")
        self.assertEqual(ml.pick("Hi", {"gu": "  "}, "gu"), "Hi")
        self.assertEqual(ml.pick("Hi", None, "hi"), "Hi")
        self.assertEqual(
            ml.clean_translations('{"gu": " a ", "xx": "b", "hi": 5, "ta": ""}'),
            {"gu": "a"},
        )
        self.assertEqual(ml.clean_translations("not json"), {})

    def test_request_language_reads_site_language_cookies(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.COOKIES["padosi_lang"] = "gu"
        self.assertEqual(ml.request_language(req), "gu")
        req = rf.get("/")
        req.COOKIES["googtrans"] = "/en/ta"
        self.assertEqual(ml.request_language(req), "ta")
        req = rf.get("/")
        req.COOKIES["padosi_lang"] = "zz"
        self.assertEqual(ml.request_language(req), "en")

    def test_translation_dropping_a_placeholder_or_link_is_rejected(self):
        text = "Hi {name}, see https://padosiagent.com/x and {{review_link}}"
        reply = {
            "gu": "નમસ્તે {name}, જુઓ https://padosiagent.com/x અને {{review_link}}",
            "hi": "नमस्ते, देखें https://padosiagent.com/x और {{review_link}}",  # lost {name}
        }
        with mock.patch.object(ml, "_ask_llm", return_value=reply) as ask:
            out = ml.translate_texts(text, ["gu", "hi"])
        self.assertEqual(set(out), {"gu"})
        ask.assert_called_once()
        # Cached: no second LLM call for Gujarati.
        with mock.patch.object(ml, "_ask_llm", side_effect=AssertionError("cached")):
            self.assertEqual(ml.translate_texts(text, ["gu"]), {"gu": reply["gu"]})

    def test_llm_failure_returns_nothing_instead_of_raising(self):
        with mock.patch.object(ml, "_ask_llm", side_effect=RuntimeError("down")):
            self.assertEqual(ml.translate_texts("Hello", ["gu"]), {})

    def test_editor_tag_escapes_saved_translations(self):
        html = Template(
            "{% load message_lang_tags %}{% message_lang_editor 'src' 'msg_i18n' value %}"
        ).render(Context({"value": {"gu": '"><script>x</script>'}}))
        self.assertIn('name="msg_i18n"', html)
        self.assertNotIn("<script>x", html)
        self.assertEqual(html.count("<option"), 22)


class TranslateMessageEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("home:message_translate")
        self.user = User.objects.create_user("tr_agent", "tr@example.com", "x")

    def _post(self, payload):
        return self.client.post(
            self.url, data=json.dumps(payload), content_type="application/json"
        )

    def test_requires_login(self):
        self.assertEqual(self._post({"text": "Hi", "langs": ["gu"]}).status_code, 403)

    def test_validates_input(self):
        self.client.force_login(self.user)
        self.assertEqual(self._post({"text": "", "langs": ["gu"]}).status_code, 400)
        self.assertEqual(self._post({"text": "Hi", "langs": ["xx"]}).status_code, 400)
        self.assertEqual(
            self._post({"text": "Hi", "langs": ["gu"] * 9}).status_code, 400
        )
        self.assertEqual(
            self._post({"text": "x" * 2001, "langs": ["gu"]}).status_code, 400
        )

    def test_returns_translations_and_missing(self):
        self.client.force_login(self.user)
        with mock.patch.object(ml, "_ask_llm", return_value={"gu": "નમસ્તે"}):
            res = self._post({"text": "Hello", "langs": ["gu", "hi"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            res.json(), {"ok": True, "translations": {"gu": "નમસ્તે"}, "missing": ["hi"]}
        )

    def test_encoded_placeholders_pass_the_waf_and_survive(self):
        # The browser sends {{agent_name}} as {__agent_name__}; raw {{...}} from an agent is blocked by the WAF.
        self.client.force_login(self.user)
        reply = {"gu": "નમસ્તે {__agent_name__}"}
        with mock.patch.object(ml, "_ask_llm", return_value=reply):
            res = self._post({"text": "Hello {__agent_name__}", "langs": ["gu"]})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["translations"], reply)

    def test_rate_limited(self):
        self.client.force_login(self.user)
        with mock.patch.object(ml, "_ask_llm", return_value={}):
            for _ in range(60):
                self._post({"text": "Hello", "langs": ["gu"]})
            self.assertEqual(
                self._post({"text": "Hello", "langs": ["gu"]}).status_code, 429
            )
