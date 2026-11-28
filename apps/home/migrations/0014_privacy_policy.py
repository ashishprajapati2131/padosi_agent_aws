from django.db import migrations, models


def seed_privacy_policy(apps, schema_editor):
    PrivacyPolicy = apps.get_model("home", "PrivacyPolicy")
    if PrivacyPolicy.objects.exists():
        return
    from apps.home.privacy_content import (
        ADDRESS,
        COMPANY_NAME,
        CONTACT_EMAIL,
        DEFAULT_PRIVACY_BODY,
        EFFECTIVE_DATE,
        GRIEVANCE_EMAIL,
    )

    PrivacyPolicy.objects.create(
        title="Privacy Policy",
        effective_date=EFFECTIVE_DATE,
        company_name=COMPANY_NAME,
        address=ADDRESS,
        contact_email=CONTACT_EMAIL,
        grievance_email=GRIEVANCE_EMAIL,
        content=DEFAULT_PRIVACY_BODY,
        is_published=True,
    )


def unseed_privacy_policy(apps, schema_editor):
    PrivacyPolicy = apps.get_model("home", "PrivacyPolicy")
    PrivacyPolicy.objects.filter(title="Privacy Policy", is_published=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0013_update_calculator_seo_descriptions"),
    ]

    operations = [
        migrations.CreateModel(
            name="PrivacyPolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(default="Privacy Policy", max_length=255)),
                ("effective_date", models.DateField()),
                ("company_name", models.CharField(max_length=255)),
                ("address", models.CharField(max_length=500)),
                ("contact_email", models.EmailField(max_length=254)),
                ("grievance_email", models.EmailField(max_length=254)),
                ("content", models.TextField()),
                ("is_published", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "privacy_policies",
                "ordering": ["-is_published", "-updated_at", "-id"],
            },
        ),
        migrations.RunPython(seed_privacy_policy, unseed_privacy_policy),
    ]
