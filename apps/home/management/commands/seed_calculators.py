from django.core.management.base import BaseCommand
from apps.home.models.calculator import Calculator, flush_calculator_cache
from apps.home.models.calculator_category import CalculatorCategory
from apps.home.calculators.seed import seed_calculators


class Command(BaseCommand):
    help = 'Idempotently seed calculator categories and the public catalog from the code registry.'

    def handle(self, *args, **options):
        created, updated = seed_calculators(Calculator, CalculatorCategory)
        flush_calculator_cache()
        self.stdout.write(self.style.SUCCESS(
            f'Calculators seeded: {created} created, {updated} engine_ready updated.'
        ))
