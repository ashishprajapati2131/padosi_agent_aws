import re
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.services.irdai_scraper import IRDAIScraperService

logger = logging.getLogger(__name__)

PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')

@csrf_exempt
@require_POST
def verify_irdai_license(request):
    """
    Verify IRDAI License view. Handles initiation and solution phases of the lookup.
    """
    # 1. Auth and permission checks
    admin_id = _get_admin_from_session(request)
    is_admin = bool(admin_id) or request.user.is_staff or request.user.is_superuser
    if not is_admin:
        return JsonResponse({'status': 'ERROR', 'message': 'Unauthorized. Admin session required.'}, status=401)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'ERROR', 'message': 'Invalid JSON request payload.'}, status=400)

    session_id = data.get('session_id')
    captcha_solution = data.get('captcha_solution')
    pan_number = data.get('pan_number')

    # 2. Stateful resume flow
    if session_id and captcha_solution:
        captcha_solution = str(captcha_solution).strip()
        if not captcha_solution:
            return JsonResponse({'status': 'ERROR', 'message': 'CAPTCHA solution cannot be empty.'}, status=400)
            
        result = IRDAIScraperService.resume_lookup(session_id, captcha_solution)
        return JsonResponse(result)

    # 3. New lookup flow
    if not pan_number:
        return JsonResponse({'status': 'ERROR', 'message': 'PAN Number is required.'}, status=400)

    pan_number = str(pan_number).strip().upper()
    if not PAN_REGEX.match(pan_number):
        return JsonResponse({'status': 'ERROR', 'message': 'Invalid PAN format. Must be 10 characters alphanumeric (e.g. ABCDE1234F).'}, status=400)

    result = IRDAIScraperService.initiate_lookup(pan_number)
    return JsonResponse(result)
