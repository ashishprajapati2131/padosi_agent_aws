from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.localization.po import completion, write_mo


class Command(BaseCommand):
    help = "Compile locale/*/LC_MESSAGES/django.po to .mo without GNU gettext, and print completion."

    def handle(self, *args, **options):
        for po_file in sorted(
            Path(settings.LOCALE_PATHS[0]).glob("*/LC_MESSAGES/django.po")
        ):
            write_mo(po_file, po_file.with_suffix(".mo"))
            language = po_file.parent.parent.name
            done, total = completion(language)
            self.stdout.write(f"{language}: {done}/{total} translated")
