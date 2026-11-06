"""Agent Card Themes: validation, flag gating, the shared card output, admin pages."""

import io
import json
import shutil
import tempfile

from django.contrib.auth.models import AnonymousUser, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings

from apps.admin_panel.services import agent_card_themes as svc
from apps.admin_panel.tests import authenticate_client
from apps.agents.models import Agent, AgentProfile
from apps.home.models.site_setting import SiteSetting


def _flag(on):
    SiteSetting.set_value(svc.FLAG_KEY, "1" if on else "0")


def _make_agent(n=1):
    u = User.objects.create_user(f"act{n}", f"act{n}@example.com")
    a = Agent.objects.create(
        user=u,
        fullname=f"Agent {n}",
        email=f"act{n}@example.com",
        mobile=f"98765000{n:02d}",
        status="active",
    )
    AgentProfile.objects.create(
        agent=a,
        whatsapp=a.mobile,
        display_name=a.fullname,
        show_ratings=True,
        show_experience=True,
        show_client_base=True,
        show_claims_stats=True,
    )
    return Agent.objects.get(pk=a.pk)


def _render_cards(agents, path="/find-agents/"):
    req = RequestFactory().get(path)
    req.user, req.session = AnonymousUser(), {}
    return "".join(
        render_to_string(
            "partials/agent-card.html", {"agent": a, "favorite_ids": []}, request=req
        )
        for a in agents
    )


class _Base(TestCase):
    # SiteSetting caches in the file cache, which outlives each test's DB rollback.
    def setUp(self):
        SiteSetting.flush_cache()


class SanitizeDesignTests(_Base):
    def test_rejects_unsafe_values(self):
        d = svc.sanitize_design(
            {
                "card_bg": "red;}</style><script>",
                "border_color": "#ABCDEF",
                "radius": "999",
                "border_width": "x",
                "shadow": "evil",
                "label_call": "<b>Call</b>{{x}}" + "y" * 40,
                "decoration_image": "../../etc/passwd",
                "decoration_size": "5",
                "show_tags": "0",
            }
        )
        self.assertEqual(d["card_bg"], "")
        self.assertEqual(d["border_color"], "#abcdef")
        self.assertEqual(d["radius"], 32)
        self.assertIsNone(d["border_width"])
        self.assertEqual(d["shadow"], "default")
        self.assertNotIn("<", d["label_call"])
        self.assertNotIn("{", d["label_call"])
        self.assertLessEqual(len(d["label_call"]), svc.LABEL_MAX)
        self.assertEqual(d["decoration_image"], "")
        self.assertEqual(d["decoration_size"], 24)
        self.assertFalse(d["show_tags"])
        self.assertTrue(d["show_badges"])  # missing keys keep the original card

    def test_only_own_media_path_allowed(self):
        self.assertEqual(
            svc.sanitize_design({"decoration_image": "agent_card_themes/diwali_1.png"})[
                "decoration_image"
            ],
            "agent_card_themes/diwali_1.png",
        )
        for bad in (
            "agent_card_themes/x.svg",
            "https://evil.example/x.png",
            "agent_card_themes/a b.png",
            'agent_card_themes/x.png")}body{x:url("y',
        ):
            self.assertEqual(
                svc.sanitize_design({"decoration_image": bad})["decoration_image"],
                "",
                bad,
            )


class ThemeStoreTests(_Base):
    def test_flag_off_means_original_card(self):
        tid = svc.add_preset("diwali")
        svc.set_active(tid)
        _flag(False)
        self.assertFalse(svc.get_active_card_theme()["enabled"])
        _flag(True)
        theme = svc.get_active_card_theme()
        self.assertTrue(theme["enabled"])
        self.assertEqual(theme["card_bg"], "#fff8e7")

    def test_delete_active_falls_back_to_default(self):
        tid = svc.save_theme("Holi", {"card_bg": "#ffffff"})
        svc.set_active(tid)
        svc.delete_theme(tid)
        self.assertEqual(svc.get_store()["active"], svc.DEFAULT_THEME_ID)

    def test_export_import_round_trip(self):
        tid = svc.save_theme("Navratri", {"card_bg": "#123456", "label_call": "Phone"})
        data = svc.export_theme(tid)
        new_id = svc.import_theme(json.dumps(data).encode())
        self.assertNotEqual(new_id, tid)
        self.assertEqual(svc.get_theme(new_id)["design"]["label_call"], "Phone")
        with self.assertRaises(ValueError):
            svc.import_theme(b"not json")

    def test_unique_ids(self):
        a, b = svc.save_theme("Diwali", {}), svc.save_theme("Diwali", {})
        self.assertNotEqual(a, b)


class SharedCardRenderTests(_Base):
    def setUp(self):
        super().setUp()
        self.agents = [_make_agent(1), _make_agent(2)]

    def test_flag_off_renders_original_card(self):
        svc.set_active(svc.add_preset("diwali"))
        _flag(False)
        html = _render_cards(self.agents)
        self.assertNotIn("agent-card-theme", html)
        for text in (
            "View Profile",
            "Call Now",
            "WhatsApp",
            "YEARS",
            "rac-btn--whatsapp",
        ):
            self.assertIn(text, html)

    def test_flag_on_applies_theme_once_per_request(self):
        tid = svc.save_theme(
            "Test",
            {
                "card_bg": "#112233",
                "show_whatsapp_btn": False,
                "label_call": "Phone karo",
                "radius": 20,
            },
        )
        svc.set_active(tid)
        _flag(True)
        html = _render_cards(self.agents)
        self.assertEqual(html.count('id="agent-card-theme"'), 1)
        self.assertIn("background:#112233", html)
        self.assertIn("border-radius:20px", html)
        self.assertNotIn("rac-btn--whatsapp", html)
        self.assertNotIn("rac-d-btn--whatsapp", html)
        self.assertIn("Phone karo", html)
        self.assertNotIn("Call Now", html)

    def test_hidden_sections(self):
        svc.set_active(svc.save_theme("Bare", {f: False for f in svc.SHOW_FIELDS}))
        _flag(True)
        html = _render_cards(self.agents, "/find-agents/?pincode=380001")
        for cls in (
            "rac-stats-grid",
            "compare-btn",
            "favorite-btn",
            "rac-btn--profile",
            "rac-btn--call",
            "rac-match-pill",
            "rac-d-match",
            "rac-rating",
            "rac-dist-pill",
        ):
            self.assertNotIn(cls, html, cls)


@override_settings(ALLOWED_HOSTS=["testserver"])
class AdminPagesTests(_Base):
    def setUp(self):
        super().setUp()
        authenticate_client(self.client)
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        _make_agent(1)

    def test_requires_admin(self):
        from django.test import Client

        resp = Client().get("/admin/agent-card-themes/")
        self.assertEqual(resp.status_code, 302)

    def test_index_editor_and_preview(self):
        tid = svc.add_preset("holi")
        resp = self.client.get(f"/admin/agent-card-themes/?edit={tid}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Holi")
        post = {
            "theme_id": tid,
            "name": "Holi",
            "card_bg": "#ff00aa",
            "label_call": "Dial",
            **{f: "1" for f in svc.SHOW_FIELDS},
        }
        resp = self.client.post("/admin/agent-card-themes/preview/", post)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "background:#ff00aa")
        self.assertContains(resp, "Dial")
        # preview must not save anything
        self.assertNotEqual(svc.get_theme(tid)["design"]["card_bg"], "#ff00aa")

    def test_save_activate_flag_and_export(self):
        with override_settings(MEDIA_ROOT=self.media):
            from PIL import Image

            buf = io.BytesIO()
            Image.new("RGBA", (40, 40), (255, 160, 0, 255)).save(buf, "PNG")
            post = {
                "name": "Diwali 2026",
                "card_bg": "#fff8e7",
                "show_call_btn": "1",
                "decoration_file": SimpleUploadedFile(
                    "diya.png", buf.getvalue(), "image/png"
                ),
            }
            resp = self.client.post("/admin/agent-card-themes/save/", post)
        self.assertEqual(resp.status_code, 302)
        theme = svc.get_store()["themes"][0]
        self.assertTrue(
            theme["design"]["decoration_image"].startswith("agent_card_themes/")
        )
        self.assertFalse(
            theme["design"]["show_whatsapp_btn"]
        )  # unticked switch = hidden

        self.client.post(
            "/admin/agent-card-themes/activate/", {"theme_id": theme["id"]}
        )
        self.assertEqual(svc.get_store()["active"], theme["id"])
        self.client.post("/admin/agent-card-themes/flag/", {"enabled": "1"})
        self.assertTrue(svc.is_enabled())

        resp = self.client.get(f"/admin/agent-card-themes/{theme['id']}/export/")
        self.assertEqual(json.loads(resp.content)["name"], "Diwali 2026")

    def test_rejects_fake_image(self):
        with override_settings(MEDIA_ROOT=self.media):
            post = {
                "name": "Bad",
                "decoration_file": SimpleUploadedFile(
                    "x.png", b"<script>alert(1)</script>", "image/png"
                ),
            }
            self.client.post("/admin/agent-card-themes/save/", post)
        self.assertEqual(svc.get_store()["themes"], [])


def _png(w, h, color=(120, 40, 160, 255)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (w, h), color).save(buf, 'PNG')
    return buf.getvalue()


@override_settings(ALLOWED_HOSTS=['testserver'])
class FestivalShareCardTests(_Base):
    def setUp(self):
        super().setUp()
        authenticate_client(self.client)
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.agent = _make_agent(1)

    def test_greeting_and_opacity_are_sanitized(self):
        d = svc.sanitize_design({'greeting_title': '<b>Happy</b> {Diwali}' + 'x' * 60,
                                 'greeting_text': 'y' * 300, 'panel_opacity': '5'})
        self.assertNotIn('<', d['greeting_title'])
        self.assertLessEqual(len(d['greeting_title']), svc.GREETING_TITLE_MAX)
        self.assertLessEqual(len(d['greeting_text']), svc.GREETING_TEXT_MAX)
        self.assertEqual(d['panel_opacity'], 50)

    def test_background_auto_fits_and_files_are_cleaned_up(self):
        import os
        from PIL import Image
        with override_settings(MEDIA_ROOT=self.media):
            self.client.post('/admin/agent-card-themes/save/', {
                'name': 'Diwali', 'greeting_title': 'Happy Diwali', **{f: '1' for f in svc.SHOW_FIELDS},
                'background_file': SimpleUploadedFile('art.png', _png(1600, 900), 'image/png'),
                'decoration_file': SimpleUploadedFile('diya.png', _png(60, 60), 'image/png'),
            })
            theme = svc.get_store()['themes'][0]
            bg = os.path.join(self.media, theme['design']['background_image'])
            self.assertEqual(Image.open(bg).size, (1200, 630))  # any upload is cover-fitted
            deco = os.path.join(self.media, theme['design']['decoration_image'])
            self.client.post('/admin/agent-card-themes/delete/', {'theme_id': theme['id']})
            self.assertFalse(os.path.exists(bg))
            self.assertFalse(os.path.exists(deco))

    def test_theme_changes_share_image_cache_key_and_url_version(self):
        from apps.agents.models import og_image_cache_key
        from apps.agents.services.og_image import card_version
        key, version = og_image_cache_key(self.agent.id), card_version(self.agent)
        svc.set_active(svc.save_theme('Colours only', {'card_bg': '#112233'}))
        _flag(True)
        self.assertEqual(og_image_cache_key(self.agent.id), key)  # nothing on the share image changed
        svc.set_active(svc.add_preset('diwali'))
        self.assertNotEqual(og_image_cache_key(self.agent.id), key)
        self.assertNotEqual(card_version(self.agent), version)
        _flag(False)
        self.assertEqual(og_image_cache_key(self.agent.id), key)

    def test_festival_share_image_renders(self):
        from PIL import Image
        from apps.agents.services.og_image import _render_agent_og_jpeg_pillow, active_share_theme
        with override_settings(MEDIA_ROOT=self.media):
            self.client.post('/admin/agent-card-themes/save/', {
                'name': 'Holi', 'greeting_title': 'Happy Holi', 'greeting_text': 'Colourful wishes',
                **{f: '1' for f in svc.SHOW_FIELDS},
                'background_file': SimpleUploadedFile('art.png', _png(800, 800, (250, 80, 160, 255)), 'image/png'),
            })
            svc.set_active(svc.get_store()['themes'][0]['id'])
            _flag(True)
            theme = active_share_theme()
            self.assertIsNotNone(theme)
            plain = _render_agent_og_jpeg_pillow(self.agent)
            festive = _render_agent_og_jpeg_pillow(self.agent, theme=theme)
            self.assertNotEqual(plain, festive)
            self.assertEqual(Image.open(io.BytesIO(festive)).size, (1200, 630))
            resp = self.client.get(f'/og-image/{self.agent.id}/preview.jpg?nocache=1')
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.content[:2], b'\xff\xd8')

    def test_preview_includes_share_image(self):
        tid = svc.add_preset('diwali')
        post = {'theme_id': tid, 'name': 'Diwali', 'greeting_title': 'Happy Diwali', **{f: '1' for f in svc.SHOW_FIELDS}}
        resp = self.client.post('/admin/agent-card-themes/preview/', post)
        self.assertContains(resp, 'id="share-img"')
        self.assertContains(resp, 'data:image/jpeg;base64,')

    def test_upload_box_accepts_an_image_as_a_new_theme(self):
        import os
        from PIL import Image
        with override_settings(MEDIA_ROOT=self.media):
            resp = self.client.post('/admin/agent-card-themes/import/', {
                'name': '', 'theme_file': SimpleUploadedFile('diwali-2026.png', _png(900, 1200), 'image/png')})
            self.assertEqual(resp.status_code, 302)
            theme = svc.get_store()['themes'][0]
            self.assertEqual(theme['name'], 'Diwali 2026')
            self.assertEqual(Image.open(os.path.join(self.media, theme['design']['background_image'])).size, (1200, 630))
            # a non-image, non-JSON file is refused and leaves nothing behind
            self.client.post('/admin/agent-card-themes/import/', {
                'theme_file': SimpleUploadedFile('x.png', b'not an image', 'image/png')})
            self.assertEqual(len(svc.get_store()['themes']), 1)


@override_settings(ALLOWED_HOSTS=['testserver'])
class DiwaliSampleThemeTests(_Base):
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_preset_ships_its_art_and_festive_layout(self):
        import os
        with override_settings(MEDIA_ROOT=self.media):
            d = svc.get_theme(svc.add_preset('diwali'))['design']
            self.assertEqual(d['share_layout'], 'festive')
            for field in ('background_image', 'decoration_image'):
                self.assertTrue(os.path.isfile(os.path.join(self.media, d[field])), field)

    def test_invalid_layout_falls_back_to_classic(self):
        self.assertEqual(svc.sanitize_design({'share_layout': 'evil'})['share_layout'], 'classic')

    def test_festive_card_renders_for_full_blank_and_long_name_agents(self):
        from PIL import Image
        from apps.agents.models import Agent, AgentPerformanceStat
        from apps.agents.services.og_image import _render_agent_og_jpeg_pillow, active_share_theme
        with override_settings(MEDIA_ROOT=self.media):
            svc.set_active(svc.add_preset('diwali'))
            _flag(True)
            theme = active_share_theme()
            self.assertEqual(theme['share_layout'], 'festive')
            full = _make_agent(1)
            full.client_base = '500'
            full.save()
            AgentPerformanceStat.objects.create(agent=full, claims_processed=9782, claims_amount=100000000)
            blank = Agent.objects.create(fullname='B', email='b@example.com', mobile='9800000011', status='pending')
            long_name = _make_agent(2)
            long_name.profile.display_name = 'Venkata Subramanian Ramakrishnan Iyer Narayanaswamy'
            long_name.profile.save()
            for agent in (full, blank, long_name):
                jpeg = _render_agent_og_jpeg_pillow(agent, theme=theme)
                self.assertEqual(Image.open(io.BytesIO(jpeg)).size, (1200, 630))
            # classic layout is untouched by the festive code
            classic = dict(theme, share_layout='classic')
            self.assertNotEqual(_render_agent_og_jpeg_pillow(full, theme=classic), _render_agent_og_jpeg_pillow(full, theme=theme))
