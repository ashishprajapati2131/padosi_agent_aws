import logging
import json
from django.http import JsonResponse
from .dashboard import _get_admin_from_session
from ..services import delete_service

logger = logging.getLogger(__name__)

# Explicit allowlist: only these models can be deleted through admin_delete.
DELETE_HANDLERS = {
    "agent": delete_service.delete_agent,
    "agent_draft": delete_service.delete_agent_draft,
    "user": delete_service.delete_user,
    "lead": delete_service.delete_lead,
    "promo_code": delete_service.delete_promo_code,
    "Faq": delete_service.delete_faq,
}


def _log_delete(request, model, record_id, outcome, snapshot=None, severity="CRITICAL"):
    from apps.admin_panel.models import AdminActivityLog

    try:
        model_id = int(record_id)
    except (TypeError, ValueError):
        model_id = None
    details = {
        "outcome": outcome,
        "snapshot": snapshot or {},
    }
    AdminActivityLog.log(
        f"Admin delete: {model}",
        model_type=model,
        model_id=model_id,
        details=details,
        request=request,
        severity=severity,
        snapshot=snapshot,
    )


def admin_delete(request):
    """
    Phase 6B.5: Generic admin delete handler
    Replaces delete_agent() and supports multiple models matching Laravel's AdminDeleteController.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Invalid request method"}, status=400
        )

    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    try:
        if request.content_type == "application/json":
            data = json.loads(request.body)
            record_id = data.get("id")
            model = data.get("model")
        else:
            record_id = request.POST.get("id")
            model = request.POST.get("model")
    except Exception:
        return JsonResponse(
            {"success": False, "message": "Invalid data format"}, status=400
        )

    if not model or not record_id:
        return JsonResponse(
            {"success": False, "message": "Missing model or id"}, status=400
        )

    try:
        handler = DELETE_HANDLERS.get(model)
        if handler is None:
            return JsonResponse(
                {"success": False, "message": "Invalid model type"}, status=400
            )
        try:
            snapshot = handler(record_id)
        except delete_service.RecordNotFound as e:
            return JsonResponse({"success": False, "message": str(e)}, status=404)
        except delete_service.AgentSoftDeleted as e:
            _log_delete(
                request,
                model,
                record_id,
                "soft-deleted (payment records kept)",
                snapshot=e.snapshot,
            )
            return JsonResponse(
                {
                    "success": True,
                    "message": "This agent has payment records, so the agent was marked deleted and the records were kept.",
                }
            )

        # Log the deletion with complete snapshot
        logger.info(
            f"Admin deleted record: model={model}, record_id={record_id}, admin_id={admin_id}, ip={request.META.get('REMOTE_ADDR')}"
        )
        _log_delete(
            request, model, record_id, "deleted", snapshot=snapshot, severity="CRITICAL"
        )

        return JsonResponse({"success": True, "message": "Record deleted successfully"})
    except Exception as e:
        logger.error(f"Admin delete failed: {e}")
        return JsonResponse(
            {"success": False, "message": "Failed to delete record: " + str(e)},
            status=500,
        )
