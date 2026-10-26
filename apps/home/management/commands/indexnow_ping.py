from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

INDEXNOW_ENDPOINT = 'https://api.indexnow.org/indexnow'
BATCH_SIZE = 10000  # IndexNow limit per request


def sitemap_urls(base):
    """Every URL /sitemap.xml lists, built from the same Sitemap classes."""
    from padosi_agent.sitemaps import sitemaps
    urls = []
    for sitemap_class in sitemaps.values():
        sitemap = sitemap_class()
        for item in sitemap.items():
            urls.append(base + sitemap.location(item))
    return list(dict.fromkeys(urls))


class Command(BaseCommand):
    help = 'Submit sitemap URLs (or --url ones) to IndexNow (Bing, Yandex). Manual, one-off.'

    def add_arguments(self, parser):
        parser.add_argument('--url', action='append', default=[],
                            help='Submit only this URL (repeatable). Default: every sitemap URL.')
        parser.add_argument('--dry-run', action='store_true',
                            help='List the URLs that would be sent; send nothing.')

    def handle(self, *args, **options):
        key = settings.INDEXNOW_KEY
        base = settings.APP_URL
        if not key:
            raise CommandError('INDEXNOW_KEY is not set in .env')
        if not base.startswith('https://'):
            raise CommandError(f'APP_URL must be the live https site, got {base!r}')
        host = urlparse(base).hostname

        urls = options['url'] or sitemap_urls(base)
        foreign = [u for u in urls if urlparse(u).hostname != host]
        if foreign:
            raise CommandError(f'URLs must be on {host}: {foreign[:3]}')
        if not urls:
            self.stdout.write('No URLs to submit.')
            return

        if options['dry_run']:
            for u in urls:
                self.stdout.write(u)
            self.stdout.write(self.style.WARNING(f'Dry run: {len(urls)} URLs, nothing sent.'))
            return

        for start in range(0, len(urls), BATCH_SIZE):
            batch = urls[start:start + BATCH_SIZE]
            payload = {'host': host, 'key': key, 'keyLocation': f'{base}/{key}.txt', 'urlList': batch}
            try:
                resp = requests.post(INDEXNOW_ENDPOINT, json=payload, timeout=30)
            except requests.RequestException as exc:
                raise CommandError(f'IndexNow request failed: {exc}')
            # 200 = accepted, 202 = accepted, key check pending.
            if resp.status_code not in (200, 202):
                raise CommandError(f'IndexNow returned {resp.status_code}: {resp.text[:200]}')
            self.stdout.write(self.style.SUCCESS(f'Submitted {len(batch)} URLs (HTTP {resp.status_code}).'))
