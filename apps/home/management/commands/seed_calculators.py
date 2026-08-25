from django.core.management.base import BaseCommand
from apps.home.models.calculator import Calculator, flush_calculator_cache
from apps.home.models.calculator_category import CalculatorCategory
from apps.home.calculators.seed import seed_calculators
from apps.home.calculators.registry import CALCULATORS, DEFAULT_CATEGORIES


class Command(BaseCommand):
    help = 'Idempotently seed calculator categories and the public catalog from the code registry.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--activate-all',
            action='store_true',
            help='Turn on every engine-ready calculator and category (use after a DB merge wiped the catalog).',
        )

    def handle(self, *args, **options):
        activate_all = bool(options.get('activate_all'))
        created, updated = seed_calculators(
            Calculator, CalculatorCategory, activate_all=activate_all,
        )
        if activate_all:
            live = Calculator.objects.filter(
                slug__in=[item['slug'] for item in CALCULATORS],
                engine_ready=True,
            ).update(is_active=True)
            cats = CalculatorCategory.objects.filter(
                slug__in=[item['slug'] for item in DEFAULT_CATEGORIES],
            ).update(is_active=True)
            self.stdout.write(self.style.WARNING(
                f'Activated {live} calculators and {cats} categories.'
            ))
        flush_calculator_cache()
        total = Calculator.objects.filter(is_active=True, engine_ready=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Calculators seeded: {created} created, {updated} updated. '
            f'Public live count: {total}/{len(CALCULATORS)}.'
        ))
