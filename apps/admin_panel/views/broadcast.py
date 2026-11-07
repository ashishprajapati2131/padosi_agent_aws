from django.shortcuts import render, redirect
from django.contrib import messages
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models import AdminActivityLog, AdminBroadcast
from apps.admin_panel.services.broadcast_service import (
    TARGETS,
    queue_broadcast,
    target_agents,
)


def broadcast_index(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    agent_counts = {key: target_agents(key).count() for key in TARGETS}

    # Fetch recent broadcasts, handle gracefully if table is missing
    recent_broadcasts = []
    try:
        recent_broadcasts = list(AdminBroadcast.objects.order_by("-created_at")[:5])
        for b in recent_broadcasts:
            b.target_label = TARGETS.get(b.target, b.target)
    except Exception:
        pass

    context = {
        "agentCounts": agent_counts,
        "recentBroadcasts": recent_broadcasts,
    }

    return render(request, "admin/broadcast.html", context)


def send_broadcast(request):
    admin = _get_admin_from_session(request)
    if not admin:
        return redirect("admin_login_page")

    if request.method != "POST":
        return redirect("broadcast_index")

    target = request.POST.get("target")
    subject = request.POST.get("subject", "").strip()
    message = request.POST.get("message", "").strip()
    channels = (
        request.POST.getlist("channels[]")
        or request.POST.getlist("channels")
        or ["email"]
    )

    if target not in TARGETS or not subject or not message:
        messages.error(request, "Target, Subject, and Message are required.")
        return redirect("broadcast_index")

    agent_ids = list(target_agents(target).values_list("id", flat=True))
    if not agent_ids:
        messages.error(request, "No active agents match the selected target.")
        return redirect("broadcast_index")

    # Row first, so a sent broadcast is always recorded; delivery fills in sent_count.
    broadcast = AdminBroadcast.objects.create(
        subject=subject,
        message=message,
        target=target,
        channels=",".join(channels),
        sent_count=0,
    )
    AdminActivityLog.log(
        action=f"Broadcast queued: '{subject}'",
        model_type="Broadcast",
        model_id=broadcast.pk,
        details={"target": target, "channels": channels, "recipients": len(agent_ids)},
        request=request,
    )
    queue_broadcast(broadcast.pk, agent_ids, subject, message, channels, target)

    messages.success(
        request,
        f"Broadcast is being sent to {len(agent_ids)} agent(s) in the background. "
        "The sent count in Recent Broadcasts updates when delivery finishes.",
    )
    return redirect("broadcast_index")
