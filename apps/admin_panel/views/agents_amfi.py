import re
import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.services.amfi_scraper import AMFIScraperService

logger = logging.getLogger(__name__)

ARN_INPUT_REGEX = re.compile(r'^(?:ARN-)?(\d+)$', re.IGNORECASE)

@csrf_exempt
@require_POST
def verify_amfi_arn(request):
    """
    Verify AMFI ARN view. Normalizes the input, starts background Playwright worker,
    and returns parsed/mapped fields and social media URLs.
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

    arn_number = data.get('arn_number', '').replace(' ', '')
    if not arn_number:
        return JsonResponse({'status': 'ERROR', 'message': 'Please enter a valid AMFI ARN Number.'}, status=400)

    match = ARN_INPUT_REGEX.match(arn_number)
    if not match:
        return JsonResponse({'status': 'ERROR', 'message': 'Please enter a valid AMFI ARN Number.'}, status=400)

    # Normalize to ARN-123456
    normalized_arn = f"ARN-{match.group(1)}"

    # Execute Playwright scraper
    result = AMFIScraperService.perform_lookup(normalized_arn)
    return JsonResponse(result)
