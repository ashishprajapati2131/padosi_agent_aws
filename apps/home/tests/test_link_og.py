from django.test import TestCase, RequestFactory
from django.core.cache import cache
from apps.home.models.site_setting import SiteSetting
from apps.home.models.link_og_setting import LinkOgSetting
from apps.home.context_processors import seo_context


class LinkOgSettingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_default_og_image_from_site_setting(self):
        SiteSetting.set_value('og_default_image', '/media/og/global_banner.jpg', group='seo')
        rf = RequestFactory()
        req = rf.get('/about/')
        ctx = seo_context(req)

        self.assertIn('/media/og/global_banner.jpg', ctx['default_og_image'])
        self.assertFalse(ctx['has_custom_link_og'])

    def test_custom_link_og_override_for_specific_path(self):
        SiteSetting.set_value('og_default_image', '/media/og/global_banner.jpg', group='seo')

        # Add custom rule for /events/paldi/
        LinkOgSetting.objects.create(
            path='/events/paldi/',
            image='https://images.example.com/paldi_poster.jpg',
            title='Paldi Special Event',
            description='Join us in Paldi for 48 hours!',
            is_active=True
        )

        rf = RequestFactory()
        
        # Test exact path
        req1 = rf.get('/events/paldi/')
        ctx1 = seo_context(req1)
        self.assertEqual(ctx1['default_og_image'], 'https://images.example.com/paldi_poster.jpg')
        self.assertEqual(ctx1['default_meta_title'], 'Paldi Special Event')
        self.assertEqual(ctx1['default_meta_description'], 'Join us in Paldi for 48 hours!')
        self.assertTrue(ctx1['has_custom_link_og'])

        # Test without trailing slash
        req2 = rf.get('/events/paldi')
        ctx2 = seo_context(req2)
        self.assertEqual(ctx2['default_og_image'], 'https://images.example.com/paldi_poster.jpg')
        self.assertTrue(ctx2['has_custom_link_og'])

        # Test another unrelated page (should fall back to global default)
        req3 = rf.get('/contact/')
        ctx3 = seo_context(req3)
        self.assertIn('/media/og/global_banner.jpg', ctx3['default_og_image'])
        self.assertFalse(ctx3['has_custom_link_og'])

    def test_inactive_link_og_rule_falls_back(self):
        SiteSetting.set_value('og_default_image', '/media/og/global_banner.jpg', group='seo')

        LinkOgSetting.objects.create(
            path='/promo/',
            image='/media/og/promo.png',
            is_active=False
        )

        rf = RequestFactory()
        req = rf.get('/promo/')
        ctx = seo_context(req)

        # Should fall back to global default because rule is inactive
        self.assertIn('/media/og/global_banner.jpg', ctx['default_og_image'])
        self.assertFalse(ctx['has_custom_link_og'])

    def test_admin_link_og_save_and_delete(self):
        from unittest.mock import patch
        from apps.admin_panel.views.settings import link_og_save, link_og_delete, link_og_toggle

        rf = RequestFactory()

        with patch('apps.admin_panel.views.settings._get_admin_from_session', return_value=1), \
             patch('django.contrib.messages.success'), \
             patch('django.contrib.messages.error'):

            # 1. Create rule via POST
            req = rf.post('/admin/settings/seo/link-og/save/', {
                'path': '/campaign/special/',
                'image_url': 'https://example.com/special.jpg',
                'title': 'Special Campaign',
                'description': 'Exclusive Offer',
                'is_active': '1'
            })
            link_og_save(req)

            rule = LinkOgSetting.objects.filter(path='/campaign/special/').first()
            self.assertIsNotNone(rule)
            self.assertEqual(rule.image, 'https://example.com/special.jpg')
            self.assertTrue(rule.is_active)

            # 2. Toggle rule
            req_toggle = rf.post(f'/admin/settings/seo/link-og/{rule.id}/toggle/')
            link_og_toggle(req_toggle, rule.id)
            rule.refresh_from_db()
            self.assertFalse(rule.is_active)

            # 3. Delete rule
            req_del = rf.post(f'/admin/settings/seo/link-og/{rule.id}/delete/')
            link_og_delete(req_del, rule.id)
            self.assertFalse(LinkOgSetting.objects.filter(path='/campaign/special/').exists())

    def test_optimize_and_format_og_image_service(self):
        import io
        from PIL import Image
        from apps.home.services.og_image_card import optimize_and_format_og_image

        # Create a square dummy image (like the one that got cropped in WhatsApp)
        raw_img = Image.new('RGB', (600, 600), (30, 140, 100))
        buf = io.BytesIO()
        raw_img.save(buf, format='PNG')
        buf.seek(0)
        buf.name = 'test_logo.png'

        saved_url = optimize_and_format_og_image(buf, 'test_logo.png', style='smart_fit', folder='og')
        self.assertTrue(saved_url.startswith('/media/og/'))
        self.assertTrue(saved_url.endswith('.jpg'))




