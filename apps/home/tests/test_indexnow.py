from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

KEY = 'a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6'


@override_settings(ALLOWED_HOSTS=['*'])
class IndexNowKeyFileTests(TestCase):
    @override_settings(INDEXNOW_KEY=KEY)
    def test_key_file_served(self):
        response = self.client.get(f'/{KEY}.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), KEY)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))

    @override_settings(INDEXNOW_KEY=KEY)
    def test_wrong_key_is_404(self):
        self.assertEqual(self.client.get('/wrongkey123.txt').status_code, 404)

    @override_settings(INDEXNOW_KEY='')
    def test_feature_off_is_404(self):
        self.assertEqual(self.client.get(f'/{KEY}.txt').status_code, 404)

    def test_robots_txt_still_works(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Sitemap:', response.content.decode())


@override_settings(INDEXNOW_KEY=KEY, APP_URL='https://padosiagent.com')
class IndexNowPingCommandTests(TestCase):
    def test_dry_run_lists_sitemap_urls_and_sends_nothing(self):
        out = StringIO()
        with mock.patch('apps.home.management.commands.indexnow_ping.requests.post') as post:
            call_command('indexnow_ping', '--dry-run', stdout=out)
        post.assert_not_called()
        self.assertIn('https://padosiagent.com/about/', out.getvalue())
        self.assertIn('Dry run', out.getvalue())

    def test_posts_payload(self):
        with mock.patch('apps.home.management.commands.indexnow_ping.requests.post') as post:
            post.return_value.status_code = 200
            call_command('indexnow_ping', '--url', 'https://padosiagent.com/about/', stdout=StringIO())
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['host'], 'padosiagent.com')
        self.assertEqual(payload['key'], KEY)
        self.assertEqual(payload['keyLocation'], f'https://padosiagent.com/{KEY}.txt')
        self.assertEqual(payload['urlList'], ['https://padosiagent.com/about/'])

    def test_rejects_other_host(self):
        with self.assertRaises(CommandError):
            call_command('indexnow_ping', '--url', 'https://example.com/x/', stdout=StringIO())

    def test_error_status_raises(self):
        with mock.patch('apps.home.management.commands.indexnow_ping.requests.post') as post:
            post.return_value.status_code = 403
            post.return_value.text = 'key not valid'
            with self.assertRaises(CommandError):
                call_command('indexnow_ping', '--url', 'https://padosiagent.com/about/', stdout=StringIO())

    @override_settings(INDEXNOW_KEY='')
    def test_refuses_without_key(self):
        with self.assertRaises(CommandError):
            call_command('indexnow_ping', '--dry-run', stdout=StringIO())
