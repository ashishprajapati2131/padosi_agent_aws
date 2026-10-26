"""
WhatsApp Agent Bot — Live Interactive & Automated Simulator

Run this script to test the complete WhatsApp Automation:
1. Automated full flow test:
     python simulate_wa_bot.py --auto

2. Interactive chat simulation (type like real WhatsApp):
     python simulate_wa_bot.py

3. Test Admin Panel ON/OFF toggle impact:
     python simulate_wa_bot.py --toggle-test
"""

import os
import sys
import json
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
import django
django.setup()

import logging
logging.getLogger('apps.wa_agent_bot').setLevel(logging.WARNING)

from django.test import RequestFactory
from apps.home.models.site_setting import SiteSetting
from apps.wa_agent_bot.models import WaBotSession, WaBotMessageLog
from apps.wa_agent_bot.views import webhook_receiver, bot_health, is_wa_bot_enabled
import apps.wa_agent_bot.views
import apps.wa_agent_bot.services.payment_service
import apps.wa_agent_bot.services.message_sender

# Mock outbound HTTP send so local simulation runs in milliseconds without requiring active OpenWA server
def _mock_send(phone, text):
    return {'success': True, 'simulated': True}

apps.wa_agent_bot.views.send_text_message = _mock_send
apps.wa_agent_bot.services.payment_service.send_text_message = _mock_send
apps.wa_agent_bot.services.message_sender.send_text_message = _mock_send
apps.wa_agent_bot.views._check_rate_limit = lambda phone: True


def send_simulated_message(phone, text):
    """Simulates an incoming WhatsApp message payload from OpenWA into webhook_receiver."""
    factory = RequestFactory()
    payload = {
        "event": "message:received",
        "data": {
            "from": f"{phone}@c.us",
            "body": text,
            "type": "chat",
        }
    }
    request = factory.post(
        '/wa-bot/webhook/',
        data=json.dumps(payload),
        content_type='application/json',
    )
    response = webhook_receiver(request)
    return response


def get_last_bot_reply(phone):
    """Fetches the latest outgoing message recorded for this session."""
    session = WaBotSession.objects.filter(phone_number=phone).first()
    if not session:
        return "(No session created)"
    last_log = session.message_logs.filter(direction=WaBotMessageLog.DIRECTION_OUT).order_by('-created_at').first()
    return last_log.content if last_log else "(No outgoing message logged)"


def run_auto_test():
    """Simulates a complete new agent journey from greeting to payment link & commands."""
    test_phone = "919999988888"
    print("\n" + "="*70)
    print("🚀 STARTING AUTOMATED WHATSAPP AGENT BOT SIMULATION")
    print("="*70)

    # Clean old test data & reset rate limiter
    from django.core.cache import cache
    from apps.agents.models import Agent
    cache.delete(f"wa_bot_rl_{test_phone}")
    WaBotSession.objects.filter(phone_number=test_phone).delete()
    Agent.objects.filter(email__startswith="test.rajesh").delete()

    unique_email = f"test.rajesh_{int(time.time())}@padosiagent.com"
    unique_mobile = f"99{int(time.time()) % 100000000:08d}"

    registration_steps = [
        ("1. Agent says Hi", "Hi"),
        ("2. Agent gives Full Name", "Rajesh Sharma"),
        ("3. Agent gives Email", unique_email),
        ("4. Agent gives Mobile", unique_mobile),
        ("5. Agent selects State", "Gujarat"),
        ("6. Agent gives Pincode", "380015"),
        ("7. Agent chooses Experience (2-5 yrs)", "2"),
        ("8. Agent selects Segments (Health & Motor)", "1, 3"),
        ("9. Agent confirms details", "yes"),
        ("10. Agent chooses Starter Plan", "1"),
    ]

    for label, user_msg in registration_steps:
        print(f"\n▶ [{label}]")
        print(f"👤 User: {user_msg}")
        send_simulated_message(test_phone, user_msg)
        time.sleep(0.1)
        bot_reply = get_last_bot_reply(test_phone)
        print(f"🤖 Bot Reply:\n{bot_reply}")
        print("-" * 50)

    # Simulate payment completion & credential delivery
    session = WaBotSession.objects.filter(phone_number=test_phone).first()
    sub_id = session.registration_data.get('subscription_id') if session else None
    if sub_id:
        print(f"\n▶ [11. Simulating Razorpay Payment Success for Subscription #{sub_id}]")
        from apps.wa_agent_bot.services.payment_service import activate_agent_subscription_after_payment
        success, msg = activate_agent_subscription_after_payment(sub_id, payment_id="pay_sim_999")
        print(f"💳 Activation Result: {msg}")
        bot_reply = get_last_bot_reply(test_phone)
        print(f"🤖 Bot Credential Reply:\n{bot_reply}")
        print("-" * 50)

    # Post-login bounded commands & polite boundary testing
    post_login_steps = [
        ("12. Agent asks for Help / Menu", "help"),
        ("13. Agent checks Profile details", "profile"),
        ("14. Agent checks Dashboard link", "dashboard"),
        ("15. Agent checks Referral link", "referral"),
        ("16. Agent asks Out-of-Scope question (Polite Refusal)", "Can you book a flight for me?"),
    ]

    for label, user_msg in post_login_steps:
        print(f"\n▶ [{label}]")
        print(f"👤 User: {user_msg}")
        send_simulated_message(test_phone, user_msg)
        time.sleep(0.1)
        bot_reply = get_last_bot_reply(test_phone)
        print(f"🤖 Bot Reply:\n{bot_reply}")
        print("-" * 50)

    print("\n" + "="*70)
    session = WaBotSession.objects.filter(phone_number=test_phone).first()
    print("✅ SIMULATION COMPLETE!")
    print(f"📌 Session State: {session.state if session else 'None'}")
    print(f"📌 Registered Data in DB: {json.dumps(session.registration_data if session else {}, indent=2)}")
    print(f"📌 Total Messages Logged: {session.message_logs.count() if session else 0}")
    print("="*70 + "\n")


def run_toggle_test():
    """Tests the Admin Panel ON/OFF flag."""
    print("\n" + "="*70)
    print("🧪 TESTING ADMIN PANEL ON/OFF TOGGLE BEHAVIOR")
    print("="*70)

    # 1. Turn ON
    SiteSetting.set_value('wa_agent_bot_enabled', True, group='general')
    print(f"1. Admin sets wa_agent_bot_enabled = True (ON)")
    print(f"   is_wa_bot_enabled() => {is_wa_bot_enabled()}")
    resp = send_simulated_message("919999900000", "hello")
    print(f"   Webhook response: {resp.content.decode('utf-8')}")

    # 2. Turn OFF
    SiteSetting.set_value('wa_agent_bot_enabled', False, group='general')
    print(f"\n2. Admin sets wa_agent_bot_enabled = False (OFF)")
    print(f"   is_wa_bot_enabled() => {is_wa_bot_enabled()}")
    resp = send_simulated_message("919999900000", "hello")
    print(f"   Webhook response: {resp.content.decode('utf-8')}")

    # Reset back to ON
    SiteSetting.set_value('wa_agent_bot_enabled', True, group='general')
    print(f"\n3. Restored wa_agent_bot_enabled = True (ON)")
    print("="*70 + "\n")


def run_interactive_chat():
    """Allows interactive terminal chat as if talking on WhatsApp."""
    test_phone = "919876500001"
    print("\n" + "="*70)
    print("💬 INTERACTIVE WHATSAPP BOT CHAT SIMULATOR")
    print(f"Phone Number: {test_phone}")
    print("Type your messages below (or type 'exit' / 'quit' to end, 'reset' to clear session):")
    print("="*70 + "\n")

    while True:
        try:
            user_msg = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting simulator.")
            break

        if not user_msg:
            continue
        if user_msg.lower() in ('exit', 'quit'):
            print("Simulator closed.")
            break
        if user_msg.lower() == 'reset':
            WaBotSession.objects.filter(phone_number=test_phone).delete()
            print("Session cleared! Send 'hi' to start fresh.")
            continue

        send_simulated_message(test_phone, user_msg)
        bot_reply = get_last_bot_reply(test_phone)
        print(f"\n🤖 Bot:\n{bot_reply}")


if __name__ == '__main__':
    if '--auto' in sys.argv:
        run_auto_test()
    elif '--toggle-test' in sys.argv:
        run_toggle_test()
    else:
        # If running in non-interactive environment, run auto test
        if not sys.stdin.isatty():
            run_auto_test()
        else:
            run_interactive_chat()
