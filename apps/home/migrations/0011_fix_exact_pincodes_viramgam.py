from decimal import Decimal
from django.db import migrations


def update_curated_pincodes(apps, schema_editor):
    from apps.home.services.distance import EXACT_PINCODE_COORDS
    from apps.home.models import Pincode, PincodeCache
    from django.core.cache import cache

    for pin, data in EXACT_PINCODE_COORDS.items():
        try:
            office_name = data.get('office_name') or f"PIN {pin}"
            district = data.get('district') or ''
            state = data.get('state') or 'Gujarat'
            taluk = data.get('taluk') or ''
            lat = Decimal(str(round(data['lat'], 8)))
            lng = Decimal(str(round(data['lng'], 8)))

            Pincode.objects.update_or_create(
                pincode=pin,
                defaults={
                    'office_name': office_name,
                    'district': district,
                    'state': state,
                    'latitude': lat,
                    'longitude': lng,
                    'taluk': taluk,
                }
            )
            try:
                cache.delete(f'pincode_row_{pin}')
                cache.delete(f'pincode_fetch_json_{pin}')
                PincodeCache.store_coordinates(
                    pin, float(lat), float(lng), f"{office_name}, {district}".strip(', ')
                )
            except Exception:
                pass
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0010_alter_upcomingfeature_visible_to'),
    ]

    operations = [
        migrations.RunPython(update_curated_pincodes, migrations.RunPython.noop),
    ]
