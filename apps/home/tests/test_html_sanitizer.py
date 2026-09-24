from django.template import Context, Template
from django.test import SimpleTestCase, TestCase

from apps.home.html_sanitizer import sanitize_html


class KeepsEditorContentTests(SimpleTestCase):
    """Everything CMS editors legitimately use must render as before."""

    def test_plain_text_is_returned_unchanged(self):
        for text in ('Digitally empower insurance agents.', 'Tom &amp; Jerry', 'a > b', ''):
            self.assertEqual(sanitize_html(text), text)

    def test_formatting_links_images_and_styles_are_kept(self):
        html = (
            '<h2 class="title">Terms</h2><p style="color: #18529d;">Hello <strong>world</strong><br>'
            '<a href="https://padosiagent.com/x" target="_blank">link</a> '
            '<a href="/find-agents/">rel</a> <a href="mailto:a@b.com">m</a> <a href="tel:+911234">t</a></p>'
            '<img src="/media/a.png" alt="a"><img src="data:image/png;base64,AAAA" alt="b">'
            '<ul><li>one</li><li>two</li></ul><table><tr><td>1</td></tr></table>'
        )
        out = sanitize_html(html)
        for piece in ('<h2 class="title">', 'style="color: #18529d;"', '<strong>world</strong>',
                      'href="https://padosiagent.com/x"', 'target="_blank"', 'href="/find-agents/"',
                      'href="mailto:a@b.com"', 'href="tel:+911234"', 'src="/media/a.png"',
                      'src="data:image/png;base64,AAAA"', '<li>two</li>', '<td>1</td>'):
            self.assertIn(piece, out)

    def test_feature_name_with_br_and_svg_icon_are_kept(self):
        self.assertIn('<br/>', sanitize_html('Digital<br>Card'))
        icon = '<svg viewBox="0 0 24 24" width="28"><path d="M12 2L2 7" fill="#fff"></path></svg>'
        out = sanitize_html(icon)
        self.assertIn('<svg', out)
        self.assertIn('<path d="M12 2L2 7" fill="#fff">', out)

    def test_style_block_and_iframe_embed_are_kept(self):
        out = sanitize_html('<style>.a > .b { color: red; }</style><iframe src="https://www.youtube.com/embed/x"></iframe>')
        self.assertIn('.a > .b { color: red; }', out)
        self.assertIn('<iframe src="https://www.youtube.com/embed/x">', out)

    def test_hero_heading_spans_are_kept(self):
        html = 'Find <span class="pa-heading-trusted">Trusted</span> <span class="pa-heading-highlight">Padosi</span> Agents'
        self.assertEqual(sanitize_html(html), html)


class RemovesScriptTests(SimpleTestCase):
    def assertNoScript(self, html):
        """No executable construct survives (checked on the parsed output:
        escaped text inside an attribute value is inert and may remain)."""
        from bs4 import BeautifulSoup
        from bs4.element import Comment
        out = sanitize_html(html)
        low = out.lower()
        for bad in ('<script', '<object', '<embed', '<base', '<meta', '<math', '<!--'):
            self.assertNotIn(bad, low, (html, out))
        soup = BeautifulSoup(out, 'html.parser')
        self.assertFalse(soup.find_all(string=lambda s: isinstance(s, Comment)), out)
        for tag in soup.find_all(True):
            if tag.name == 'style':
                self.assertNotIn('<', tag.get_text(), out)
            for attr, value in tag.attrs.items():
                value = ' '.join(value) if isinstance(value, list) else str(value)
                norm = ''.join(value.split()).lower()
                self.assertFalse(attr.lower().startswith('on'), (html, out))
                self.assertNotIn(attr.lower(), ('srcdoc',), (html, out))
                self.assertNotIn('javascript:', norm, (html, out))
                self.assertNotIn('vbscript:', norm, (html, out))
                self.assertNotIn('expression(', norm, (html, out))
                if attr.lower() in ('href', 'src', 'action', 'formaction', 'xlink:href'):
                    self.assertFalse(norm.startswith('data:') and not norm.startswith('data:image/'), (html, out))
        return low

    def test_script_and_event_handlers_removed(self):
        out = self.assertNoScript('<p>Hi<script>alert(1)</script><img src="x.png" onerror="alert(1)"></p>')
        self.assertIn('<img src="x.png"/>', out)
        self.assertIn('hi', out)

    def test_dangerous_urls_removed(self):
        for html in (
            '<a href="javascript:alert(1)">x</a>',
            '<a href="  JaVaScRiPt:alert(1)">x</a>',
            '<a href="jav&#x61;script:alert(1)">x</a>',
            '<a href="java\tscript:alert(1)">x</a>',
            '<a href="data:text/html,<script>alert(1)</script>">x</a>',
            '<iframe src="javascript:alert(1)"></iframe>',
            '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
            '<form action="javascript:alert(1)"><button formaction="javascript:alert(1)">b</button></form>',
            '<svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>',
            '<svg><animate attributeName="href" values="javascript:alert(1)"></animate></svg>',
        ):
            self.assertNoScript(html)

    def test_parser_differential_tricks_removed(self):
        for html in (
            '<!-- --!><img src=x onerror=alert(1)> -->',
            '<img/src/onerror=alert(1)>',
            '<svg><style><img src=x onerror=alert(1)></style></svg>',
            '<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>',
            '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>',
            '<object data="x.swf"></object><embed src="x.swf"><base href="https://evil.example/">',
            '<meta http-equiv="refresh" content="0;url=https://evil.example/">',
            '<div style="background:url(javascript:alert(1))">x</div>',
            '<div style="width: expression(alert(1))">x</div>',
            '<style>body { background: url("javascript:alert(1)") }</style>',
        ):
            self.assertNoScript(html)

    def test_escaped_markup_inside_attributes_stays_escaped(self):
        out = sanitize_html('<p title="</p><img src=x onerror=alert(1)>">x</p>')
        self.assertNotIn('<img', out)
        out = sanitize_html('<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>')
        self.assertNotIn('</noscript><img', out)
        self.assertNotIn('<img', out)


class ActiveContentDetectionTests(SimpleTestCase):
    def test_detects_scripts_in_every_form(self):
        from apps.home.html_sanitizer import has_active_content
        for html in (
            '<script>alert(1)</script>',
            '<SCRIPT src="https://x.example/a.js"></SCRIPT>',
            '<svg><script>alert(1)</script></svg>',
            '<img src=x onerror=alert(1)>',
            '<img/src/onerror=alert(1)>',
            '<img title=">" onerror="alert(1)">',
            '<a href="javascript:alert(1)">x</a>',
            '<a href="jav&#x61;script:alert(1)">x</a>',
            '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>',
            '<!-- --!><img src=x onerror=alert(1)> -->',
            '<object data="x.swf"></object>',
            '<embed src="x.swf">',
        ):
            self.assertTrue(has_active_content(html), html)

    def test_plain_pages_are_not_flagged(self):
        from apps.home.html_sanitizer import has_active_content
        for html in (
            '',
            'Just text about agent onboarding = easy',
            '<!DOCTYPE html><html><head><meta charset="utf-8"><title>T</title>'
            '<style>.a > .b { color: red }</style></head><body><h1>Hi</h1>'
            '<a href="https://padosiagent.com/">home</a><img src="/media/a.png">'
            '<iframe src="https://www.youtube.com/embed/x"></iframe></body></html>',
        ):
            self.assertFalse(has_active_content(html), html)


class RawPageScriptPolicyTests(SimpleTestCase):
    class _Page:
        def __init__(self, content, is_raw_code=True):
            self.content = content
            self.is_raw_code = is_raw_code

    def test_policy(self):
        from apps.admin_panel.views.pages import raw_script_save_blocked
        script = '<html><body><script>track()</script></body></html>'
        plain = '<html><body><h1>Hi</h1></body></html>'
        # Super Admin: always allowed.
        self.assertFalse(raw_script_save_blocked(True, True, script))
        # Staff: new or changed script content is blocked...
        self.assertTrue(raw_script_save_blocked(False, True, script))
        self.assertTrue(raw_script_save_blocked(False, True, script, self._Page(plain)))
        self.assertTrue(raw_script_save_blocked(False, True, script, self._Page(script, is_raw_code=False)))
        # ...but raw HTML without scripts, non-raw pages, and re-saving an
        # existing script page unchanged (title/SEO/status edits) still work.
        self.assertFalse(raw_script_save_blocked(False, True, plain))
        self.assertFalse(raw_script_save_blocked(False, False, script))
        self.assertFalse(raw_script_save_blocked(False, True, script.replace('\n', '\r\n'), self._Page(script)))


class RawPageServingTests(TestCase):
    def test_existing_raw_page_is_served_byte_for_byte(self):
        from apps.home.models.page import Page
        content = '<!DOCTYPE html><html><body><div id="faq"></div><script>document.getElementById("faq").textContent="ok"</script></body></html>'
        Page.objects.create(title='Raw', slug='raw-test-page', content=content, is_active=True, is_raw_code=True)
        resp = self.client.get('/raw-test-page/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode('utf-8'), content)

    def test_normal_page_strips_scripts(self):
        from apps.home.models.page import Page
        Page.objects.create(title='Normal', slug='normal-test-page', is_active=True, is_raw_code=False,
                            content='<p>Hello <strong>there</strong></p><script>alert(1)</script>')
        resp = self.client.get('/normal-test-page/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, '<p>Hello <strong>there</strong></p>', html=False)
        self.assertNotContains(resp, 'alert(1)')


class CleanHtmlFilterTests(SimpleTestCase):
    def test_filter_marks_output_safe_and_cleans(self):
        tpl = Template('{% load html_tags %}{{ v|clean_html }}')
        out = tpl.render(Context({'v': '<b>ok</b><script>alert(1)</script>'}))
        self.assertEqual(out, '<b>ok</b>')

    def test_filter_handles_none_and_default_html(self):
        tpl = Template('{% load html_tags %}{{ v|default:"<strong>Padosi</strong>Agent"|clean_html }}')
        self.assertEqual(tpl.render(Context({'v': None})), '<strong>Padosi</strong>Agent')
