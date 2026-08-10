"""
Participants (contest registration) + Facebook share module.

Ports of:
- App\\Http\\Controllers\\ParticipantController          (routes/web.php:547-551)
- App\\Http\\Controllers\\Frontend\\FacebookPostController (routes/web.php:554-569)
- App\\Models\\Participant

The participants table is owned by the Laravel schema (managed=False); the
Facebook connection columns were added to it via migration 0014.
"""

import logging
import os
import re
import uuid

import requests as http_requests
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.agents.models import Participant

logger = logging.getLogger(__name__)

GRAPH_BASE = 'https://graph.facebook.com/v19.0'
FACEBOOK_APP_ID = getattr(settings, 'FACEBOOK_APP_ID', '759405373797845')
FACEBOOK_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', '')


def _validation_failure(errors):
    """Laravel-style 422: {success, message, errors: {field: [msg]}}."""
    return JsonResponse({
        'success': False,
        'message': 'Please fix the validation errors below.',
        'errors': errors,
    }, status=422)


def _participant_json(participant):
    return {
        'id': participant.id,
        'full_name': participant.full_name,
        'email': participant.email,
        'phone_number': participant.phone_number,
        'have_insurance': participant.have_insurance,
        'insurance_products': participant.insurance_products,
        'insurance_planning': participant.insurance_planning,
        'mutual_fund': participant.mutual_fund,
        'mf_plan': participant.mf_plan,
        'thank_my_padosi': participant.thank_my_padosi,
        'thank_my_padosi_for': participant.thank_my_padosi_for,
        'participant_shared': participant.participant_shared,
        'shareable_id': participant.shareable_id,
        'registration_completed_at': participant.registration_completed_at,
        'created_at': participant.created_at,
        'updated_at': participant.updated_at,
    }


# ────────────────────────────────────────────────────────────
# Participants module — ParticipantController
# ────────────────────────────────────────────────────────────

@require_GET
def participants_create(request):
    """GET /participants/create — the registration form lives on the coming-soon page."""
    return redirect('home:coming_soon')


def participants_router(request):
    """Method dispatch for /participants — POST → store, GET → index (Laravel routes
    web.php:548-549 share the same path with different HTTP verbs)."""
    if request.method == 'POST':
        return participants_store(request)
    return participants_index(request)


@require_GET
def participants_index(request):
    """GET /participants — plain JSON listing (no blade exists on the Laravel side)."""
    participants = Participant.objects.all().order_by('-id')
    return JsonResponse({
        'success': True,
        'count': participants.count(),
        'participants': [_participant_json(p) for p in participants[:500]],
    })


@require_POST
def participants_store(request):
    """POST /participants — contest registration (ParticipantController@store)."""
    logger.info("PARTICIPANT REGISTRATION - Received data: %s", dict(request.POST))
    full_name = (request.POST.get('full_name') or '').strip()
    email = (request.POST.get('email') or '').strip()
    phone_number = (request.POST.get('phone_number') or '').strip()
    have_insurance = request.POST.get('have_insurance')
    mutual_fund = request.POST.get('mutual_fund')

    errors = {}
    if not full_name or len(full_name) > 255:
        errors['full_name'] = ['Full name is required']
    if not email:
        errors['email'] = ['Email address is required']
    elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        errors['email'] = ['Please enter a valid email address']
    if not phone_number or len(phone_number) > 20:
        errors['phone_number'] = ['Phone number is required']
    if have_insurance not in ('yes', 'no'):
        errors['have_insurance'] = ['Please indicate if you have insurance']
    if mutual_fund not in ('yes', 'no'):
        errors['mutual_fund'] = ['Please indicate if you invest in mutual funds']
    if errors:
        return _validation_failure(errors)

    if Participant.objects.filter(email=email).exists():
        return JsonResponse({
            'success': False,
            'message': 'This email address is already registered.'
        }, status=422)
    if Participant.objects.filter(phone_number=phone_number).exists():
        return JsonResponse({
            'success': False,
            'message': 'This phone number is already registered.'
        }, status=422)

    try:
        participant_data = {
            'full_name': full_name,
            'email': email,
            'phone_number': phone_number,
            'have_insurance': have_insurance,
            'mutual_fund': mutual_fund,
            'thank_my_padosi': request.POST.get('thank_my_Padosi'),
            'thank_my_padosi_for': request.POST.get('thank_my_Padosi_for'),
            'shareable_id': f"part_{uuid.uuid4().hex[:13]}",
            'registration_completed_at': None,
            'participant_shared': 'No',
        }

        if have_insurance == 'yes':
            participant_data['insurance_products'] = request.POST.getlist('products[]') or request.POST.getlist('products') or []
            participant_data['insurance_planning'] = None
        else:
            participant_data['insurance_products'] = None
            participant_data['insurance_planning'] = request.POST.get('planning')

        if mutual_fund == 'no':
            participant_data['mf_plan'] = request.POST.get('mf_plan')
        else:
            participant_data['mf_plan'] = None

        participant = Participant.objects.create(**participant_data)
    except Exception as e:
        logger.error("PARTICIPANT REGISTRATION - Error: %s", e, exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'Registration failed. Please try again.'
        }, status=500)

    logger.info("PARTICIPANT REGISTRATION - Participant created: %s", participant.id)
    share_url = request.build_absolute_uri(f'/participants/share/{participant.shareable_id}/')
    return JsonResponse({
        'success': True,
        'message': 'Registration completed successfully!',
        'participant': _participant_json(participant),
        'shareable_id': participant.shareable_id,
        'share_url': share_url,
    }, status=201)


@require_GET
def participant_share(request, shareable_id):
    """GET /participants/share/{shareableId} — public share page (ParticipantController@share)."""
    participant = get_object_or_404(Participant, shareable_id=shareable_id)
    logger.info("PARTICIPANT SHARE - Page accessed: %s", shareable_id)
    return render(request, 'participants/share.html', {'participant': participant})


@require_GET
def participant_show(request, participant_id):
    """GET /participants/{participant} — ParticipantController@show (model-bound by id)."""
    participant = get_object_or_404(Participant, id=participant_id)
    return render(request, 'participants/share.html', {'participant': participant})


@require_POST
def mark_as_shared(request, shareable_id):
    """POST /participants/{shareableId}/mark-shared — ParticipantController@markAsShared."""
    participant = Participant.objects.filter(shareable_id=shareable_id).first()
    if not participant:
        return JsonResponse({'success': False, 'message': 'Participant not found'}, status=404)

    if participant.is_shared():
        return JsonResponse({'success': True, 'message': 'Already confirmed!'})

    participant.mark_as_shared()
    logger.info("PARTICIPANT SHARED - Updated to Yes: %s", shareable_id)
    return JsonResponse({
        'success': True,
        'message': 'Thank you for sharing! Your participation has been confirmed.'
    })


# ────────────────────────────────────────────────────────────
# Facebook share module — FacebookPostController
# ────────────────────────────────────────────────────────────

def _get_participant_or_error(request):
    participant_id = request.POST.get('participant_id')
    if not participant_id or not str(participant_id).isdigit():
        return None, _validation_failure({'participant_id': ['The participant id field is required.']})
    participant = Participant.objects.filter(id=participant_id).first()
    if not participant:
        return None, _validation_failure({'participant_id': ['The selected participant id is invalid.']})
    return participant, None


def _facebook_post(url, data):
    try:
        resp = http_requests.post(url, data=data, timeout=15)
        return resp.status_code, resp.json()
    except Exception as e:
        logger.error("Facebook API error: %s", e)
        return 500, {'error': {'message': str(e)}}


def _facebook_get(url, params):
    try:
        resp = http_requests.get(url, params=params, timeout=15)
        return resp.status_code, resp.json()
    except Exception as e:
        logger.error("Facebook API error: %s", e)
        return 500, {'error': {'message': str(e)}}


@require_POST
def facebook_auto_post(request):
    """POST api/facebook/auto-post — FacebookPostController@autoPost."""
    errors = {}
    if not request.POST.get('participant_id'):
        errors['participant_id'] = ['The participant id field is required.']
    if not request.POST.get('message'):
        errors['message'] = ['The message field is required.']
    link = (request.POST.get('link') or '').strip()
    if not link or not re.match(r'^https?://', link):
        errors['link'] = ['The link field is required.']
    if errors:
        return _validation_failure(errors)

    participant, err = _get_participant_or_error(request)
    if err:
        return err

    if not participant.facebook_access_token:
        return JsonResponse({
            'success': False,
            'message': 'Facebook not connected. Please connect Facebook first.',
            'action_required': 'facebook_connect',
        }, status=400)

    status_code, result = _facebook_post(f'{GRAPH_BASE}/me/feed', {
        'message': request.POST.get('message'),
        'link': link,
        'access_token': participant.facebook_access_token,
    })

    if status_code == 500:
        return JsonResponse({
            'success': False,
            'message': f'Auto-post failed: {result.get("error", {}).get("message", "Unknown error")}',
        }, status=500)

    if result.get('id'):
        Participant.objects.filter(id=participant.id).update(
            status='completed', facebook_post_id=result['id']
        )
        logger.info("Facebook auto-post successful", extra={'participant_id': participant.id, 'facebook_post_id': result['id']})
        return JsonResponse({
            'success': True,
            'message': 'Post created successfully on Facebook!',
            'post_id': result['id'],
            'post_url': f"https://facebook.com/{result['id']}",
        })

    error_message = result.get('error', {}).get('message', 'Unknown Facebook error')
    logger.error("Facebook auto-post failed: %s", error_message)
    return JsonResponse({
        'success': False,
        'message': f'Facebook posting failed: {error_message}',
        'facebook_error': result.get('error'),
    }, status=400)


@require_POST
def facebook_verify_post(request):
    """POST api/facebook/verify-post — FacebookPostController@verifyPost."""
    errors = {}
    if not request.POST.get('participant_id'):
        errors['participant_id'] = ['The participant id field is required.']
    if not request.POST.get('post_id'):
        errors['post_id'] = ['The post id field is required.']
    if errors:
        return _validation_failure(errors)

    participant, err = _get_participant_or_error(request)
    if err:
        return err

    if not participant.facebook_access_token:
        return JsonResponse({'success': False, 'message': 'Facebook not connected'}, status=400)

    status_code, post_data = _facebook_get(f"{GRAPH_BASE}/{request.POST['post_id']}", {
        'fields': 'id,message,created_time,privacy,is_published',
        'access_token': participant.facebook_access_token,
    })

    if status_code == 500:
        return JsonResponse({
            'success': False,
            'message': f'Verification failed: {post_data.get("error", {}).get("message", "Unknown error")}',
        }, status=500)

    if 'error' in post_data:
        return JsonResponse({
            'success': False,
            'message': f"Post not found: {post_data['error'].get('message', 'Unknown error')}",
        }, status=404)

    is_public = post_data.get('privacy', {}).get('value') == 'EVERYONE'
    is_published = bool(post_data.get('is_published', False))

    if is_published:
        Participant.objects.filter(id=participant.id).update(status='verified')

    logger.info("Facebook post verification", extra={
        'participant_id': participant.id,
        'post_id': request.POST['post_id'],
        'is_public': is_public,
        'is_published': is_published,
    })
    return JsonResponse({
        'success': True,
        'post': post_data,
        'is_public': is_public,
        'is_published': is_published,
        'verification_status': 'verified' if is_published else 'pending',
    })


@require_POST
def facebook_store_token(request):
    """POST api/facebook/store-token — FacebookPostController@storeAccessToken."""
    errors = {}
    if not request.POST.get('participant_id'):
        errors['participant_id'] = ['The participant id field is required.']
    if not request.POST.get('access_token'):
        errors['access_token'] = ['The access token field is required.']
    if not request.POST.get('user_id'):
        errors['user_id'] = ['The user id field is required.']
    if errors:
        return _validation_failure(errors)

    participant, err = _get_participant_or_error(request)
    if err:
        return err

    status_code, user_data = _facebook_get(f'{GRAPH_BASE}/me', {
        'fields': 'id,name',
        'access_token': request.POST['access_token'],
    })

    if status_code == 500:
        return JsonResponse({
            'success': False,
            'message': f'Failed to connect Facebook: {user_data.get("error", {}).get("message", "Unknown error")}',
        }, status=500)

    if status_code != 200:
        return JsonResponse({'success': False, 'message': 'Invalid access token'}, status=400)

    Participant.objects.filter(id=participant.id).update(
        facebook_access_token=request.POST['access_token'],
        facebook_user_id=user_data.get('id'),
        status='connected',
    )
    logger.info("Facebook access token stored", extra={
        'participant_id': participant.id,
        'facebook_user_id': user_data.get('id'),
    })
    return JsonResponse({
        'success': True,
        'message': 'Facebook connected successfully!',
        'user': user_data,
    })


@require_GET
def facebook_connection_status(request, participant_id):
    """GET api/facebook/connection-status/{participantId} — FacebookPostController@getConnectionStatus."""
    participant = Participant.objects.filter(id=participant_id).first()
    if not participant:
        return JsonResponse({'success': False, 'message': 'Participant not found'}, status=404)

    is_connected = bool(participant.facebook_access_token and participant.facebook_user_id)
    return JsonResponse({
        'success': True,
        'data': {
            'connected': is_connected,
            'facebook_user_id': participant.facebook_user_id,
            'participant_status': participant.status,
            'has_posted': bool(participant.facebook_post_id),
        },
    })


def _extract_post_id_from_url(url):
    """Port of FacebookPostController::extractPostIdFromUrl."""
    patterns = [
        r'facebook\.com\/.+\/posts\/(\d+)',
        r'facebook\.com\/.+\/activity\/(\d+)',
        r'facebook\.com\/photo\.php\?fbid=(\d+)',
        r'facebook\.com\/permalink\.php\?story_fbid=(\d+)&',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


@require_POST
def facebook_confirm_manual_share(request):
    """POST api/facebook/confirm-manual-share — FacebookPostController@confirmManualShare."""
    errors = {}
    if not request.POST.get('participant_id'):
        errors['participant_id'] = ['The participant id field is required.']
    post_url = (request.POST.get('post_url') or '').strip()
    if not post_url or not re.match(r'^https?://', post_url):
        errors['post_url'] = ['The post url field is required.']

    screenshot = request.FILES.get('screenshot')
    if screenshot:
        if screenshot.size > 5 * 1024 * 1024:
            errors['screenshot'] = ['The screenshot must not be greater than 5 MB.']
        else:
            ext = os.path.splitext(screenshot.name)[1].lower()
            if ext not in ('.jpeg', '.jpg', '.png'):
                errors['screenshot'] = ['The screenshot must be a file of type: jpeg, png, jpg.']
    if errors:
        return _validation_failure(errors)

    participant, err = _get_participant_or_error(request)
    if err:
        return err

    screenshot_path = None
    if screenshot:
        try:
            screenshot_path = default_storage.save(f'screenshots/{uuid.uuid4().hex}{os.path.splitext(screenshot.name)[1].lower()}', screenshot)
        except Exception as e:
            logger.error("Screenshot save failed: %s", e)

    post_id = _extract_post_id_from_url(post_url)

    update_data = {
        'status': 'completed',
        'facebook_post_url': post_url,
        'manual_share': True,
    }
    if post_id:
        update_data['facebook_post_id'] = post_id
    if screenshot_path:
        update_data['screenshot_path'] = screenshot_path

    Participant.objects.filter(id=participant.id).update(**update_data)
    logger.info("Manual share confirmed", extra={'participant_id': participant.id, 'post_url': post_url})

    return JsonResponse({
        'success': True,
        'message': 'Manual share confirmed successfully!',
        'data': {
            'screenshot_url': f"{settings.MEDIA_URL}{screenshot_path}" if screenshot_path else None,
            'post_url': post_url,
        },
    })
