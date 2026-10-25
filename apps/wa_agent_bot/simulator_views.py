"""
WhatsApp Agent Bot — Interactive Web Simulator Views
Provides a live WhatsApp Web mockup in the browser for testing.
"""

import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from apps.home.models.site_setting import SiteSetting
from .models import WaBotSession, WaBotMessageLog
from .views import is_wa_bot_enabled
from .services.state_machine import process_message
from .services.payment_service import activate_agent_subscription_after_payment

logger = logging.getLogger(__name__)

SIMULATOR_PHONE = "919876543210"


@require_GET
def simulator_page(request):
    """Renders the WhatsApp Web Simulator page."""
    enabled = is_wa_bot_enabled()
    session = WaBotSession.objects.filter(phone_number=SIMULATOR_PHONE).first()
    
    # Get recent messages if any
    recent_logs = []
    if session:
        logs = session.message_logs.order_by('created_at')[:50]
        for log in logs:
            recent_logs.append({
                'direction': log.direction,
                'content': log.content,
                'time': log.created_at.strftime('%I:%M %p'),
            })

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Bot Live Simulator — PadosiAgent</title>
    <link href="https://fonts.googleapis.com/css2?family=Segoe+UI:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif;
            background: #111b21;
            color: #e9edef;
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        /* Top Navigation Bar */
        .top-navbar {{
            background: #202c33;
            border-bottom: 1px solid #2a3942;
            padding: 10px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 13px;
        }}
        .top-nav-left {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo-tag {{
            background: #25D366;
            color: #0c1317;
            font-weight: 800;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 11px;
            letter-spacing: 0.5px;
            text-transform: uppercase;
        }}
        .top-links {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .top-link {{
            color: #aebac1;
            text-decoration: none;
            padding: 5px 12px;
            border-radius: 6px;
            background: rgba(255,255,255,0.05);
            transition: all 0.2s;
            font-size: 12px;
        }}
        .top-link:hover {{
            background: rgba(255,255,255,0.1);
            color: #ffffff;
        }}
        .status-pill {{
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
        }}
        .status-active {{
            background: rgba(37, 211, 102, 0.15);
            color: #25D366;
            border: 1px solid #25D366;
        }}
        .status-disabled {{
            background: rgba(239, 68, 68, 0.15);
            color: #ef4444;
            border: 1px solid #ef4444;
        }}
        /* Main Container */
        .main-container {{
            flex: 1;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 15px;
            background: #0c1317;
            overflow: hidden;
        }}
        /* Phone Frame */
        .phone-wrapper {{
            width: 100%;
            max-width: 520px;
            height: 100%;
            max-height: 860px;
            background: #0b141a;
            border: 1px solid #222e35;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.7);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        /* Chat Header */
        .chat-header {{
            background: #202c33;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid #222e35;
        }}
        .chat-header-info {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .avatar {{
            width: 44px;
            height: 44px;
            border-radius: 50%;
            background: linear-gradient(135deg, #25D366 0%, #128C7E 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            color: #ffffff;
            font-weight: 700;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
        }}
        .header-title {{
            font-size: 16px;
            font-weight: 600;
            color: #e9edef;
        }}
        .header-status {{
            font-size: 12px;
            color: #8696a0;
            display: flex;
            align-items: center;
            gap: 5px;
        }}
        .header-status.online::before {{
            content: '';
            display: inline-block;
            width: 8px;
            height: 8px;
            background: #25D366;
            border-radius: 50%;
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .btn-header {{
            background: rgba(255,255,255,0.08);
            border: 1px solid rgba(255,255,255,0.1);
            color: #e9edef;
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
        }}
        .btn-header:hover {{
            background: rgba(255,255,255,0.15);
        }}
        /* Chat Body */
        .chat-body {{
            flex: 1;
            padding: 16px;
            overflow-y: auto;
            background: #0b141a url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png') repeat;
            background-size: 380px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        /* Chat Bubbles */
        .msg-row {{
            display: flex;
            width: 100%;
        }}
        .msg-row.in {{
            justify-content: flex-start;
        }}
        .msg-row.out {{
            justify-content: flex-end;
        }}
        .bubble {{
            max-width: 82%;
            padding: 8px 12px;
            border-radius: 10px;
            font-size: 14.2px;
            line-height: 1.45;
            position: relative;
            word-wrap: break-word;
            white-space: pre-wrap;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
        }}
        .bubble.in {{
            background: #202c33;
            color: #e9edef;
            border-top-left-radius: 0px;
        }}
        .bubble.out {{
            background: #005c4b;
            color: #e9edef;
            border-top-right-radius: 0px;
        }}
        .bubble a {{
            color: #53bdeb;
            text-decoration: underline;
            word-break: break-all;
        }}
        .bubble b, .bubble strong {{
            font-weight: 700;
            color: #ffffff;
        }}
        .bubble .time {{
            float: right;
            margin-left: 10px;
            margin-top: 4px;
            font-size: 11px;
            color: #8696a0;
        }}
        .bubble .pay-btn {{
            display: block;
            margin-top: 10px;
            padding: 8px 14px;
            background: #25D366;
            color: #0b141a !important;
            font-weight: 700;
            text-align: center;
            border-radius: 8px;
            text-decoration: none !important;
            box-shadow: 0 2px 6px rgba(37, 211, 102, 0.3);
        }}
        /* Quick Chips Area */
        .quick-chips-wrapper {{
            background: #202c33;
            border-top: 1px solid #2a3942;
            padding: 8px 12px;
            display: flex;
            gap: 6px;
            overflow-x: auto;
            white-space: nowrap;
        }}
        .quick-chips-wrapper::-webkit-scrollbar {{
            height: 4px;
        }}
        .quick-chips-wrapper::-webkit-scrollbar-thumb {{
            background: #2a3942;
            border-radius: 4px;
        }}
        .chip {{
            background: #111b21;
            color: #25D366;
            border: 1px solid #2a3942;
            padding: 5px 12px;
            border-radius: 16px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-family: inherit;
        }}
        .chip:hover {{
            background: #25D366;
            color: #111b21;
            border-color: #25D366;
        }}
        .chip.pay-action {{
            background: #0284c7;
            color: #ffffff;
            border-color: #0284c7;
        }}
        .chip.pay-action:hover {{
            background: #0369a1;
        }}
        /* Input Bar */
        .chat-input-bar {{
            background: #202c33;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .chat-input {{
            flex: 1;
            background: #2a3942;
            border: none;
            outline: none;
            color: #d1d7db;
            font-size: 14.5px;
            padding: 10px 16px;
            border-radius: 8px;
            font-family: inherit;
        }}
        .chat-input::placeholder {{
            color: #8696a0;
        }}
        .btn-send {{
            background: #00a884;
            color: #ffffff;
            border: none;
            width: 42px;
            height: 42px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            transition: all 0.2s;
        }}
        .btn-send:hover {{
            background: #06cf9c;
            transform: scale(1.05);
        }}
        .disabled-notice {{
            background: #ef4444;
            color: #ffffff;
            text-align: center;
            padding: 6px 12px;
            font-size: 12px;
            font-weight: 600;
            display: none;
        }}
    </style>
</head>
<body>

    <!-- Top Navigation Bar -->
    <div class="top-navbar">
        <div class="top-nav-left">
            <span class="logo-tag"><i class="fa-brands fa-whatsapp me-1"></i> WA Bot Simulator</span>
            <span style="color: #8696a0;">|</span>
            <span style="font-size: 12px; color: #aebac1;">Test Phone: <strong style="color: #25D366;">+{SIMULATOR_PHONE}</strong></span>
        </div>
        <div class="top-links">
            <button id="toggleServiceBtn" class="status-pill {'status-active' if enabled else 'status-disabled'}">
                <i class="fa-solid fa-power-off"></i>
                <span id="serviceStatusText">{'Master Switch: ON' if enabled else 'Master Switch: OFF'}</span>
            </button>
            <a href="/admin/settings/general/" target="_blank" class="top-link"><i class="fa-solid fa-sliders me-1"></i> Admin Settings</a>
            <a href="/admin/wa_agent_bot/wabotsession/" target="_blank" class="top-link"><i class="fa-solid fa-users-gear me-1"></i> Bot Sessions</a>
            <a href="/admin/wa_agent_bot/wabotmessagelog/" target="_blank" class="top-link"><i class="fa-solid fa-clock-rotate-left me-1"></i> Message Logs</a>
            <a href="/wa-bot/health/" target="_blank" class="top-link"><i class="fa-solid fa-heart-pulse me-1"></i> Health API</a>
        </div>
    </div>

    <div id="disabledBanner" class="disabled-notice" style="{'display: block;' if not enabled else 'display: none;'}">
        ⚠️ WhatsApp Bot is currently <strong>TURNED OFF</strong> via Admin Panel. Incoming messages will not be processed until turned ON.
    </div>

    <!-- Main Simulator Frame -->
    <div class="main-container">
        <div class="phone-wrapper">
            <!-- Header -->
            <div class="chat-header">
                <div class="chat-header-info">
                    <div class="avatar"><i class="fa-solid fa-robot"></i></div>
                    <div>
                        <div class="header-title">PadosiAgent Official Bot</div>
                        <div class="header-status online" id="onlineIndicator">online & ready</div>
                    </div>
                </div>
                <div class="header-actions">
                    <button class="btn-header" onclick="resetChat()"><i class="fa-solid fa-arrow-rotate-left me-1"></i> Reset</button>
                </div>
            </div>

            <!-- Chat Messages Body -->
            <div class="chat-body" id="chatBody"></div>

            <!-- Quick Action Chips -->
            <div class="quick-chips-wrapper">
                <button class="chip" onclick="sendQuick('Hi')">👋 Hi</button>
                <button class="chip" onclick="sendQuick('yes')">✅ Confirm (yes)</button>
                <button class="chip" onclick="sendQuick('1')">1️⃣ Plan 1</button>
                <button class="chip" onclick="sendQuick('2')">2️⃣ Plan 2</button>
                <button class="chip" onclick="sendQuick('3')">3️⃣ Plan 3</button>
                <button class="chip pay-action" onclick="simulatePaymentSuccess()"><i class="fa-solid fa-credit-card me-1"></i> Simulate Payment Success</button>
                <button class="chip" onclick="sendQuick('help')">📋 help</button>
                <button class="chip" onclick="sendQuick('profile')">👤 profile</button>
                <button class="chip" onclick="sendQuick('dashboard')">📊 dashboard</button>
                <button class="chip" onclick="sendQuick('referral')">🔗 referral</button>
                <button class="chip" onclick="sendQuick('status')">📈 status</button>
                <button class="chip" onclick="sendQuick('Can you book a flight for me?')">🚫 Test Refusal</button>
                <button class="chip" onclick="sendQuick('back')">⬅️ back</button>
                <button class="chip" onclick="sendQuick('cancel')">❌ cancel</button>
            </div>

            <!-- Input Bar -->
            <div class="chat-input-bar">
                <input type="text" id="msgInput" class="chat-input" placeholder="Type a message..." autofocus>
                <button class="btn-send" id="sendBtn" onclick="sendMessage()"><i class="fa-solid fa-paper-plane"></i></button>
            </div>
        </div>
    </div>

    <script>
        const initialLogs = {json.dumps(recent_logs)};
        const chatBody = document.getElementById('chatBody');
        const msgInput = document.getElementById('msgInput');
        const toggleBtn = document.getElementById('toggleServiceBtn');
        const statusText = document.getElementById('serviceStatusText');
        const banner = document.getElementById('disabledBanner');

        // Format whatsapp style markdown (*bold*, _italic_, urls)
        function formatMarkdown(text) {{
            if (!text) return '';
            let s = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            
            // *bold*
            s = s.replace(/\\*([^\\*]+)\\*/g, '<strong>$1</strong>');
            // _italic_
            s = s.replace(/_([^_]+)_/g, '<em>$1</em>');
            // `code`
            s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // URLs to links
            s = s.replace(/(https?:\\/\\/[^\\s<]+)/g, '<a href="$1" target="_blank">$1</a>');

            // If Razorpay link present, add a direct CTA button
            const rzpMatch = text.match(/(https?:\\/\\/rzp\\.io\\/[^\\s]+)/);
            if (rzpMatch) {{
                s += `<a href="${{rzpMatch[1]}}" target="_blank" class="pay-btn"><i class="fa-solid fa-lock me-1"></i> Pay Now via Razorpay &rarr;</a>`;
            }}

            return s;
        }}

        function addMessage(text, direction, timeStr) {{
            const now = timeStr || new Date().toLocaleTimeString([], {{hour: '2-digit', minute:'2-digit'}});
            const row = document.createElement('div');
            row.className = `msg-row ${{direction === 'out' ? 'out' : 'in'}}`;
            
            const bubble = document.createElement('div');
            bubble.className = `bubble ${{direction === 'out' ? 'out' : 'in'}}`;
            bubble.innerHTML = `${{formatMarkdown(text)}}<span class="time">${{now}}</span>`;

            row.appendChild(bubble);
            chatBody.appendChild(row);
            chatBody.scrollTop = chatBody.scrollHeight;
        }}

        // Render initial logs if any, or greeting
        if (initialLogs.length > 0) {{
            initialLogs.forEach(l => {{
                addMessage(l.content, l.direction === 'out' ? 'in' : 'out', l.time);
            }});
        }} else {{
            addMessage("👋 Welcome to the PadosiAgent WhatsApp Bot Live Simulator!\\n\\nType *Hi* below or click the *👋 Hi* button to start the agent registration journey.", 'in');
        }}

        // Send message
        function sendMessage() {{
            const text = msgInput.value.trim();
            if (!text) return;

            addMessage(text, 'out');
            msgInput.value = '';
            msgInput.focus();

            fetch('/wa-bot/simulator/send/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ message: text, phone: '{SIMULATOR_PHONE}' }})
            }})
            .then(res => res.json())
            .then(data => {{
                if (data.reply) {{
                    addMessage(data.reply, 'in');
                }} else if (data.status === 'disabled') {{
                    addMessage("⚠️ WhatsApp Bot service is currently DISABLED in Admin Panel. Please turn the switch ON at the top to chat.", 'in');
                }}
            }})
            .catch(err => {{
                addMessage("❌ Connection error. Please make sure the Django server is running.", 'in');
            }});
        }}

        function sendQuick(txt) {{
            msgInput.value = txt;
            sendMessage();
        }}

        function resetChat() {{
            if (!confirm('Are you sure you want to reset this chat session and start fresh?')) return;
            fetch('/wa-bot/simulator/reset/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ phone: '{SIMULATOR_PHONE}' }})
            }})
            .then(res => res.json())
            .then(data => {{
                chatBody.innerHTML = '';
                addMessage("🔄 Session reset successfully! Type *Hi* to start fresh.", 'in');
            }});
        }}

        function simulatePaymentSuccess() {{
            fetch('/wa-bot/simulator/simulate-payment/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ phone: '{SIMULATOR_PHONE}' }})
            }})
            .then(res => res.json())
            .then(data => {{
                if (data.reply) {{
                    addMessage(data.reply, 'in');
                }} else {{
                    alert(data.message || 'No pending subscription found to activate. Please choose a plan first.');
                }}
            }});
        }}

        // Enter key to send
        msgInput.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter') {{
                sendMessage();
            }}
        }});

        // Toggle service ON/OFF
        toggleBtn.addEventListener('click', function() {{
            fetch('/wa-bot/simulator/toggle/', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }}
            }})
            .then(res => res.json())
            .then(data => {{
                if (data.enabled) {{
                    toggleBtn.className = 'status-pill status-active';
                    statusText.textContent = 'Master Switch: ON';
                    banner.style.display = 'none';
                }} else {{
                    toggleBtn.className = 'status-pill status-disabled';
                    statusText.textContent = 'Master Switch: OFF';
                    banner.style.display = 'block';
                }}
            }});
        }});
    </script>
</body>
</html>
"""
    return HttpResponse(html, content_type='text/html')


@csrf_exempt
@require_POST
def simulator_send(request):
    """Processes a simulated user message from the browser UI."""
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = body.get('message', '').strip()
    phone = body.get('phone', SIMULATOR_PHONE)

    if not is_wa_bot_enabled():
        return JsonResponse({'status': 'disabled', 'message': 'WhatsApp Bot is paused via Admin Panel'})

    session, _ = WaBotSession.objects.get_or_create(
        phone_number=phone,
        defaults={
            'state': WaBotSession.STATE_WELCOME,
            'registration_data': {},
            'session_context': {},
        }
    )
    session.update_last_activity()

    # Log incoming
    WaBotMessageLog.objects.create(
        session=session,
        direction=WaBotMessageLog.DIRECTION_IN,
        content=text[:2000],
        state_at_time=session.state,
    )

    # Process via state machine
    try:
        reply = process_message(session, text)
    except Exception as e:
        logger.error(f"[WA-Bot-Simulator] Error processing message: {e}", exc_info=True)
        reply = "Sorry, an error occurred. Please try typing *restart*."

    # Log outgoing
    WaBotMessageLog.objects.create(
        session=session,
        direction=WaBotMessageLog.DIRECTION_OUT,
        content=reply[:5000],
        state_at_time=session.state,
    )
    session.save()

    return JsonResponse({
        'status': 'processed',
        'reply': reply,
        'state': session.state,
        'phone': phone,
    })


@csrf_exempt
@require_POST
def simulator_reset(request):
    """Clears the session for the simulator phone."""
    try:
        body = json.loads(request.body.decode('utf-8'))
        phone = body.get('phone', SIMULATOR_PHONE)
    except Exception:
        phone = SIMULATOR_PHONE

    WaBotSession.objects.filter(phone_number=phone).delete()
    return JsonResponse({'success': True, 'message': 'Session reset'})


@csrf_exempt
@require_POST
def simulator_payment(request):
    """Simulates payment completion for the current session."""
    try:
        body = json.loads(request.body.decode('utf-8'))
        phone = body.get('phone', SIMULATOR_PHONE)
    except Exception:
        phone = SIMULATOR_PHONE

    session = WaBotSession.objects.filter(phone_number=phone).first()
    if not session:
        return JsonResponse({'success': False, 'message': 'No session found'})

    sub_id = session.registration_data.get('subscription_id')
    if not sub_id:
        return JsonResponse({'success': False, 'message': 'No pending subscription found. Please select a plan first.'})

    success, msg = activate_agent_subscription_after_payment(sub_id, payment_id="pay_simulated_browser")
    
    # Fetch credentials message logged
    last_log = session.message_logs.filter(direction=WaBotMessageLog.DIRECTION_OUT).order_by('-created_at').first()
    reply = last_log.content if last_log else msg

    return JsonResponse({
        'success': success,
        'message': msg,
        'reply': reply,
    })


@csrf_exempt
@require_POST
def simulator_toggle(request):
    """Toggles the Master Switch ON/OFF."""
    current = bool(SiteSetting.get_value('wa_agent_bot_enabled', True))
    new_val = not current
    SiteSetting.set_value('wa_agent_bot_enabled', new_val, group='general')
    return JsonResponse({'success': True, 'enabled': new_val})
