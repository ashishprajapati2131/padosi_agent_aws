from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.cache import cache
import json
import logging
import re
from .llm_client import generate_suggestion_chips, get_chat_completion, extract_agent_links, stream_plain_text_completion
from .models import ChatMessage
import uuid

logger = logging.getLogger(__name__)

MAX_CHAT_MESSAGE_CHARS = 2000

@require_GET
def get_history(request, session_id):
    if not session_id or not re.match(r'^[a-zA-Z0-9_\-]+$', session_id) or len(session_id) > 100:
        return JsonResponse({"success": False, "error": "Invalid session identifier.", "data": []}, status=400)

    messages = ChatMessage.objects.filter(
        session__session_id=session_id,
        role__in=['user', 'assistant']
    ).exclude(content__startswith='__TOOL_CALLS__').order_by('timestamp')
    
    data = []
    for m in messages:
        if m.role == 'assistant':
            cleaned, agent_links = extract_agent_links(m.content)
            data.append({
                "role": m.role,
                "content": cleaned,
                "agent_links": agent_links,
                "agent_cards": m.agent_cards or [],
                "timestamp": m.timestamp.isoformat()
            })
        else:
            data.append({
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat()
            })
        
    return JsonResponse({
        "success": True,
        "data": data
    })

@require_GET
def get_chips(request):
    chips = cache.get("suggestion_chips")
    if not chips:
        chips = generate_suggestion_chips()
        cache.set("suggestion_chips", chips, timeout=46800) # 13 hours
    
    return JsonResponse({
        "success": True,
        "data": chips
    })

@csrf_exempt
@require_POST
def send_message(request):
    # Cross-origin protection: exact host match ("host in origin" accepted
    # e.g. https://padosiagent.com.evil.example).
    from urllib.parse import urlparse
    origin = request.headers.get('origin', '')
    host = request.get_host()
    if origin and urlparse(origin).netloc.lower() != host.lower():
        logger.warning(f"Blocked unauthorized cross-origin chatbot request from origin: {origin}")
        return JsonResponse({"success": False, "error": "Forbidden cross-origin request."}, status=403)
    # Behind the local reverse proxy REMOTE_ADDR is 127.0.0.1 for everyone, which
    # made this a single global bucket; use the trusted-proxy client IP.
    from apps.admin_panel.middleware import ThreatMonitorMiddleware
    client_ip = ThreatMonitorMiddleware.get_client_ip(request)
    
    # Rate limit: 20 messages per minute per IP using a rolling window
    rl_key = f"ratelimit_chat_{client_ip}"
    
    # FileBasedCache incr() destroys custom TTLs and lacks atomicity anyway.
    # We use a timestamp list to implement a true rolling window.
    import time
    now = time.time()
    
    timestamps = cache.get(rl_key, [])
    # Prune timestamps older than 60 seconds
    timestamps = [t for t in timestamps if t > now - 60]
    
    if len(timestamps) >= 20:
        return JsonResponse({"success": False, "error": "Too many requests. Please slow down."}, status=429)
        
    timestamps.append(now)
    cache.set(rl_key, timestamps, timeout=60)
    
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
        user_message = str(data.get("message") or "").strip()
        session_id = str(data.get("session_id") or "").strip()

        if session_id and (len(session_id) > 100 or not re.match(r'^[a-zA-Z0-9_\-]+$', session_id)):
            return JsonResponse({"success": False, "error": "Invalid session identifier."}, status=400)
        if not session_id:
            # Random chat id. This used to fall back to the Django session key,
            # which is returned to the page and works as a bearer id for chat
            # history — exposing the HttpOnly session secret to JavaScript.
            session_id = uuid.uuid4().hex

        if not user_message:
            return JsonResponse({"success": False, "error": "Message is required."}, status=400)
        if len(user_message) > MAX_CHAT_MESSAGE_CHARS:
            # Every character is billed LLM input; cap it.
            return JsonResponse({"success": False, "error": "Message is too long."}, status=400)

        def event_stream():
            """SSE generator — wraps stream_plain_text_completion and handles the use_full_flow fallback."""
            try:
                gen = stream_plain_text_completion(session_id, user_message)
                first = next(gen)

                if first.get("type") == "use_full_flow":
                    # LLM wants to make a tool call — use the full non-streaming flow.
                    # The user_message was already saved to DB by stream_plain_text_completion,
                    # so pass user_message=None to get_chat_completion to avoid double-saving.
                    result = get_chat_completion(
                        session_id, 
                        user_message=None,
                        prefilled_response_message=first.get("response_message"),
                        prefilled_tool_calls=first.get("tool_calls")
                    )
                    payload = {
                        "type": "full_response",
                        "success": result.get("success", True),
                        "session_id": session_id,
                        "reply": result["reply"],
                        "quick_options": result.get("quick_options", []),
                        "quick_option_groups": result.get("quick_option_groups", []),
                        "agent_links": result.get("agent_links", []),
                        "agent_cards": result.get("agent_cards", []),
                        "total_time": result.get("total_time", 0.0)
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    return

                # First event was a chunk or error — stream it and the rest
                yield f"data: {json.dumps(first)}\n\n"
                for event in gen:
                    yield f"data: {json.dumps(event)}\n\n"

            except Exception as e:
                import traceback
                traceback.print_exc()
                logger.error(f"Error in SSE event_stream: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': 'I am having trouble connecting right now. Please try again later.'})}\n\n"

        response = StreamingHttpResponse(event_stream(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Prevent nginx/proxy buffering
        return response

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in send_message view: {e}")
        
        # Graceful handler for MySQL emoji/encoding issues
        if "Incorrect string value" in error_msg or "utf8mb4" in error_msg:
            friendly_reply = "I'm sorry, I couldn't process some of the characters (like emojis) in your message. Could you try sending it again as plain text?"
            return JsonResponse({
                "success": True,
                "session_id": session_id,
                "data": {
                    "reply": friendly_reply,
                    "quick_options": [],
                    "agent_links": []
                }
            })
            
        return JsonResponse({"success": False, "error": "Internal server error"}, status=500)

