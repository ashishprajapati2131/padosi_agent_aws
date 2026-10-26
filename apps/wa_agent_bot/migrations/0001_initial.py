"""
Migration: Create WhatsApp Agent Bot tables.

Tables created:
  - wa_bot_sessions: Tracks conversation state per phone number
  - wa_bot_message_logs: Audit log of all bot messages
"""

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('agents', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP TABLE IF EXISTS wa_bot_message_logs;",
                "DROP TABLE IF EXISTS wa_bot_sessions;",
            ],
            reverse_sql="",
        ),
        migrations.CreateModel(
            name='WaBotSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(db_index=True, help_text='WhatsApp number in international format, e.g. 919876543210', max_length=20, unique=True)),
                ('state', models.CharField(
                    choices=[
                        ('welcome', 'Welcome'),
                        ('ask_fullname', 'Ask Full Name'),
                        ('ask_email', 'Ask Email'),
                        ('ask_mobile', 'Ask Mobile'),
                        ('ask_state', 'Ask State'),
                        ('ask_pincode', 'Ask Pincode'),
                        ('ask_experience', 'Ask Experience'),
                        ('ask_segments', 'Ask Segments'),
                        ('confirm_details', 'Confirm Details'),
                        ('ask_plan', 'Ask Plan Selection'),
                        ('awaiting_payment', 'Awaiting Payment'),
                        ('creating_account', 'Creating Account'),
                        ('registration_done', 'Registration Done'),
                        ('logged_in', 'Logged In'),
                    ],
                    db_index=True,
                    default='welcome',
                    max_length=50,
                )),
                ('registration_data', models.JSONField(blank=True, default=dict, help_text='Accumulated registration form data collected during the conversation')),
                ('is_registered', models.BooleanField(default=False, help_text='True once the agent account has been created')),
                ('is_logged_in', models.BooleanField(default=False, help_text='True once the agent has received credentials and is in post-login mode')),
                ('generated_password', models.CharField(blank=True, default='', help_text='Temporary generated password (sent once, should be changed on first login)', max_length=128)),
                ('session_context', models.JSONField(blank=True, default=dict, help_text='Temporary context data for multi-step operations')),
                ('message_count', models.PositiveIntegerField(default=0, help_text='Total messages received in this session')),
                ('last_message_at', models.DateTimeField(blank=True, help_text='Timestamp of the last incoming message', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('agent', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    help_text='Linked agent record after successful registration',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='wa_bot_sessions',
                    to='agents.agent',
                )),
            ],
            options={
                'verbose_name': 'WhatsApp Bot Session',
                'verbose_name_plural': 'WhatsApp Bot Sessions',
                'db_table': 'wa_bot_sessions',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='WaBotMessageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(choices=[('in', 'Incoming'), ('out', 'Outgoing')], max_length=3)),
                ('content', models.TextField(help_text='Message text content')),
                ('state_at_time', models.CharField(blank=True, default='', help_text='Bot state when this message was processed', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('session', models.ForeignKey(
                    db_constraint=False,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='message_logs',
                    to='wa_agent_bot.wabotsession',
                )),
            ],
            options={
                'verbose_name': 'WhatsApp Bot Message Log',
                'verbose_name_plural': 'WhatsApp Bot Message Logs',
                'db_table': 'wa_bot_message_logs',
                'ordering': ['created_at'],
            },
        ),
    ]
