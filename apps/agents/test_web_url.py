from django.test import SimpleTestCase

from apps.agents.utils.web_url import (
    normalize_web_url,
    optional_web_url_error,
    process_digital_presence_for_save,
)


class WebUrlValidationTests(SimpleTestCase):
    def test_empty_optional(self):
        self.assertEqual(optional_web_url_error('', None, 'website'), '')
        self.assertEqual(normalize_web_url(''), '')

    def test_accepts_common_formats(self):
        for raw in (
            'https://example.com',
            'http://example.com/path',
            'https://www.example.com/page?q=1',
            'www.sub.example.co.in/profile',
        ):
            self.assertEqual(optional_web_url_error(raw, None, 'website'), '', raw)

    def test_rejects_unsafe_and_malformed(self):
        for raw in (
            'javascript:alert(1)',
            'not a url',
            'https://',
            'hello world.com',
        ):
            self.assertTrue(optional_web_url_error(raw, None, 'website'), raw)

    def test_normalizes_without_scheme(self):
        self.assertEqual(normalize_web_url('www.example.com/about'), 'https://www.example.com/about')

    def test_linkedin_host_required(self):
        err = optional_web_url_error('https://example.com/in/me', ('linkedin.com',), 'LinkedIn')
        self.assertTrue(err)

    def test_process_digital_presence_normalizes(self):
        errors, values = process_digital_presence_for_save(
            website='www.example.com',
            linkedin='https://www.linkedin.com/in/agent',
        )
        self.assertEqual(errors, {})
        self.assertEqual(values['website'], 'https://www.example.com')
        self.assertEqual(values['linkedin'], 'https://www.linkedin.com/in/agent')
