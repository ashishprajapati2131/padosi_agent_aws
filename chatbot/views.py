from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.cache import cache
import json
import logging
from .llm_client import generate_suggestion_chips, get_chat_completion
from .models import ChatMessage
import uuid

logger = logging.getLogger(__name__)

@require_GET
def get_history(request, session_id):
    messages = ChatMessage.objects.filter(
        session__session_id=session_id,
        role__in=['user', 'assistant']
    ).order_by('timestamp')
    
    data = []
    for m in messages:
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
    client_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    
    # Rate limit: 20 messages per minute per IP
    rl_key = f"ratelimit_chat_{client_ip}"
    count = cache.get(rl_key, 0)
    if count >= 20:
        return JsonResponse({"success": False, "error": "Too many requests. Please slow down."}, status=429)
    cache.set(rl_key, count + 1, timeout=60)
    
    try:
        data = json.loads(request.body)
        user_message = data.get("message", "").strip()
        session_id = data.get("session_id", "").strip()
        
        if not session_id:
            if not request.session.session_key:
                request.session.create()
            session_id = request.session.session_key
            
        if not user_message:
            return JsonResponse({"success": False, "error": "Message is required."}, status=400)
            
        result = get_chat_completion(session_id, user_message)
        
        return JsonResponse({
            "success": True,
            "session_id": session_id,
            "data": {
                "reply": result["reply"],
                "quick_options": result["quick_options"]
            }
        })
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error in send_message view: {e}")
        return JsonResponse({"success": False, "error": "Internal server error"}, status=500)
