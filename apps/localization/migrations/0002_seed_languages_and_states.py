from django.db import migrations

LANGUAGES = [
    ("en", "English"),
    ("hi", "हिन्दी"),
    ("gu", "ગુજરાતી"),
    ("mr", "मराठी"),
    ("ta", "தமிழ்"),
    ("kn", "ಕನ್ನಡ"),
    ("ml", "മലയാളം"),
    ("bn", "বাংলা"),
    ("pa", "ਪੰਜਾਬੀ"),
    ("te", "తెలుగు"),
    ("or", "ଓଡ଼ିଆ"),
    ("as", "অসমীয়া"),
]

# (ISO 3166-2:IN code, name, aliases, language or None = no automatic switch)
STATES = [
    ("AN", "Andaman and Nicobar Islands", "", None),
    ("AP", "Andhra Pradesh", "", "te"),
    ("AR", "Arunachal Pradesh", "", None),
    ("AS", "Assam", "", "as"),
    ("BR", "Bihar", "", "hi"),
    ("CH", "Chandigarh", "", "hi"),
    ("CT", "Chhattisgarh", "CG", "hi"),
    ("DH", "Dadra and Nagar Haveli and Daman and Diu", "DN,DD", "gu"),
    ("DL", "Delhi", "National Capital Territory of Delhi,NCT of Delhi", "hi"),
    ("GA", "Goa", "", None),
    ("GJ", "Gujarat", "", "gu"),
    ("HR", "Haryana", "", "hi"),
    ("HP", "Himachal Pradesh", "", "hi"),
    ("JK", "Jammu and Kashmir", "", None),
    ("JH", "Jharkhand", "", "hi"),
    ("KA", "Karnataka", "", "kn"),
    ("KL", "Kerala", "", "ml"),
    ("LA", "Ladakh", "", None),
    ("LD", "Lakshadweep", "", "ml"),
    ("MP", "Madhya Pradesh", "", "hi"),
    ("MH", "Maharashtra", "", "mr"),
    ("MN", "Manipur", "", None),
    ("ML", "Meghalaya", "", None),
    ("MZ", "Mizoram", "", None),
    ("NL", "Nagaland", "", None),
    ("OR", "Odisha", "OD,Orissa", "or"),
    ("PY", "Puducherry", "Pondicherry", "ta"),
    ("PB", "Punjab", "", "pa"),
    ("RJ", "Rajasthan", "", "hi"),
    ("SK", "Sikkim", "", None),
    ("TN", "Tamil Nadu", "", "ta"),
    ("TG", "Telangana", "TS", "te"),
    ("TR", "Tripura", "", "bn"),
    ("UP", "Uttar Pradesh", "", "hi"),
    ("UT", "Uttarakhand", "UK,UL,Uttaranchal", "hi"),
    ("WB", "West Bengal", "", "bn"),
]


def seed(apps, schema_editor):
    SiteLanguage = apps.get_model("localization", "SiteLanguage")
    StateLanguage = apps.get_model("localization", "StateLanguage")
    LocalizationSettings = apps.get_model("localization", "LocalizationSettings")
    for order, (code, native) in enumerate(LANGUAGES):
        SiteLanguage.objects.get_or_create(
            code=code, defaults={"native_name": native, "sort_order": order}
        )
    for code, name, aliases, language in STATES:
        StateLanguage.objects.get_or_create(
            state_code=code,
            defaults={"state_name": name, "aliases": aliases, "language_id": language},
        )
    LocalizationSettings.objects.get_or_create(
        pk=1, defaults={"default_language_id": "en"}
    )


class Migration(migrations.Migration):
    dependencies = [("localization", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
