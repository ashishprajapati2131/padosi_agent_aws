from django.db import migrations, models


DEFAULT_FEATURES = [
    {
        'title': 'AI Assist',
        'description': 'Smart replies, instant quotes and AI-drafted follow-ups for every lead.',
        'icon': 'fa-solid fa-wand-magic-sparkles',
        'status_badge': 'next_up',
        'custom_badge_text': 'Next up',
        'visible_to': 'all',
        'sort_order': 1,
        'is_active': True,
    },
    {
        'title': 'Cross Sell Products',
        'description': 'Get suggested products for each client based on what they already own.',
        'icon': 'fa-solid fa-arrows-rotate',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 2,
        'is_active': True,
    },
    {
        'title': 'Existing Customer Servicing Tools',
        'description': 'Endorsements, nominee updates and policy service requests in one place.',
        'icon': 'fa-solid fa-headset',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 3,
        'is_active': True,
    },
    {
        'title': 'VAS for Existing Customers',
        'description': 'Health check-ups, teleconsultation and lifestyle benefits you can offer.',
        'icon': 'fa-solid fa-gift',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 4,
        'is_active': True,
    },
    {
        'title': 'Customer Retention Tools',
        'description': 'Renewal nudges, birthday wishes and win-back campaigns on autopilot.',
        'icon': 'fa-solid fa-heart-circle-check',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 5,
        'is_active': True,
    },
    {
        'title': 'Marketplace',
        'description': 'Buy leads, marketing creatives and growth services from trusted partners.',
        'icon': 'fa-solid fa-store',
        'status_badge': '',
        'custom_badge_text': '',
        'visible_to': 'all',
        'sort_order': 6,
        'is_active': True,
    },
]


def seed_upcoming_features(apps, schema_editor):
    UpcomingFeature = apps.get_model('home', 'UpcomingFeature')
    for item in DEFAULT_FEATURES:
        UpcomingFeature.objects.get_or_create(
            title=item['title'],
            defaults=item
        )


def unseed_upcoming_features(apps, schema_editor):
    UpcomingFeature = apps.get_model('home', 'UpcomingFeature')
    titles = [item['title'] for item in DEFAULT_FEATURES]
    UpcomingFeature.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('home', '0008_calculator_category'),
    ]

    operations = [
        migrations.CreateModel(
            name='UpcomingFeature',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('icon', models.CharField(default='fa-solid fa-wand-magic-sparkles', help_text="FontAwesome icon class (e.g. 'fa-solid fa-wand-magic-sparkles')", max_length=100)),
                ('status_badge', models.CharField(blank=True, choices=[('', 'No Badge'), ('next_up', 'Next up'), ('in_development', 'In development'), ('coming_soon', 'Coming soon'), ('beta', 'Beta')], default='', max_length=50)),
                ('custom_badge_text', models.CharField(blank=True, default='', help_text='Optional custom badge text', max_length=50)),
                ('visible_to', models.CharField(choices=[('all', 'All Plans (Starter & Professional)'), ('starter', 'Starter Plan Only'), ('professional', 'Professional Plan Only')], default='all', max_length=20)),
                ('sort_order', models.IntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'upcoming_features',
                'ordering': ['sort_order', 'id'],
            },
        ),
        migrations.RunPython(seed_upcoming_features, unseed_upcoming_features),
    ]
