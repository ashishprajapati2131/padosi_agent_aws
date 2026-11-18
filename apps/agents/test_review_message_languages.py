from django.test import TestCase

from apps.agents.services.google_review import (
    get_google_review_system_config,
    save_google_review_system_config,
    _text,
)
from apps.agents.services.review_growth import (
    get_review_growth_config,
    sanitize_review_growth_config,
)
from apps.home.models import SiteSetting


class ReviewMessageLanguageTests(TestCase):
    def test_google_review_translations_saved_cleaned_and_picked(self):
        save_google_review_system_config({
            "nudge_title": "Help {{agent_name}} grow!",
            "nudge_title_i18n": '{"gu": "{{agent_name}} ને મદદ કરો", "xx": "bad", "hi": "  "}',
        })
        cfg = get_google_review_system_config()
        self.assertEqual(cfg["nudge_title_i18n"], {"gu": "{{agent_name}} ને મદદ કરો"})
        self.assertEqual(_text(cfg, "nudge_title", "", "gu"), "{{agent_name}} ને મદદ કરો")
        self.assertEqual(_text(cfg, "nudge_title", "", "hi"), "Help {{agent_name}} grow!")
        self.assertEqual(cfg["nudge_message_i18n"], {})

    def test_review_growth_translations_picked_by_language(self):
        cfg = sanitize_review_growth_config({
            "upgrade_title": "Unlock",
            "upgrade_title_i18n": {"mr": "अनलॉक करा", "zz": "x"},
        })
        self.assertEqual(cfg["upgrade_title_i18n"], {"mr": "अनलॉक करा"})
        SiteSetting.set_value("review_growth_config", cfg, "pricing")
        self.assertEqual(get_review_growth_config("mr")["upgrade_title"], "अनलॉक करा")
        self.assertEqual(get_review_growth_config("ta")["upgrade_title"], "Unlock")
        self.assertEqual(get_review_growth_config()["upgrade_title"], "Unlock")
