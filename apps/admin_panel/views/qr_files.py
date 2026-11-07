import os
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, FileResponse, Http404
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.db.models import Sum
from django.conf import settings
from apps.admin_panel.views.dashboard import _get_admin_from_session
from apps.admin_panel.models.qr_file import QrFile
from apps.admin_panel.services import qr_files_service


def qr_files_index(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    query = QrFile.objects.all()

    # Search filter
    search = request.GET.get("search", "").strip()
    if search:
        query = query.filter(original_name__icontains=search)

    # Type filter
    file_type_filter = request.GET.get("type", "").strip().lower()
    if file_type_filter:
        if file_type_filter == "image":
            query = query.filter(file_type__in=["png", "jpg", "jpeg", "gif", "webp"])
        else:
            query = query.filter(file_type=file_type_filter)

    query = query.order_by("-created_at")

    # Paginate by 10
    paginator = Paginator(query, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    total_files = QrFile.objects.count()
    total_downloads = (
        QrFile.objects.aggregate(total=Sum("download_count"))["total"] or 0
    )

    # Build download URLs client-side/server-side
    for f in page_obj:
        f.download_url = request.build_absolute_uri(f"/d/{f.unique_code}")

    return render(
        request,
        "admin/qr_files/index.html",
        {
            "files": page_obj,
            "totalFiles": total_files,
            "totalDownloads": total_downloads,
            "search": search,
            "selected_type": file_type_filter,
        },
    )


def qr_files_store(request):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse(
                {"success": False, "message": "No file uploaded"}, status=400
            )

        # 512MB max check
        if uploaded_file.size > 524288000:
            return JsonResponse(
                {"success": False, "message": "File size exceeds limit of 512MB"},
                status=400,
            )

        original_name = uploaded_file.name
        name_parts = original_name.rsplit(".", 1)
        extension = name_parts[1].lower() if len(name_parts) > 1 else ""

        allowed_extensions = [
            "pdf",
            "apk",
            "zip",
            "docx",
            "xlsx",
            "pptx",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "webp",
            "rar",
            "tar",
            "gz",
            "txt",
            "csv",
            "json",
        ]
        if extension not in allowed_extensions:
            return JsonResponse(
                {"success": False, "message": "Invalid file type."}, status=422
            )

        qr_file = qr_files_service.store_qr_file(
            uploaded_file, original_name, extension
        )

        # Build download url
        download_url = request.build_absolute_uri(f"/d/{qr_file.unique_code}")

        return JsonResponse(
            {
                "success": True,
                "message": "File uploaded successfully!",
                "file": {
                    "id": qr_file.id,
                    "original_name": qr_file.original_name,
                    "formatted_size": qr_file.formatted_size,
                    "download_url": download_url,
                    "unique_code": qr_file.unique_code,
                    "created_at": qr_file.created_at.strftime("%d-%m-%Y %H:%M"),
                },
            }
        )

    return JsonResponse(
        {"success": False, "message": "Invalid request method"}, status=405
    )


def qr_files_update(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=403)

    qr_file = get_object_or_404(QrFile, id=id)

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return JsonResponse(
                {"success": False, "message": "No file uploaded"}, status=400
            )

        # 512MB max check
        if uploaded_file.size > 524288000:
            return JsonResponse(
                {"success": False, "message": "File size exceeds limit of 512MB"},
                status=400,
            )

        original_name = uploaded_file.name
        name_parts = original_name.rsplit(".", 1)
        extension = name_parts[1].lower() if len(name_parts) > 1 else ""

        allowed_extensions = [
            "pdf",
            "apk",
            "zip",
            "docx",
            "xlsx",
            "pptx",
            "png",
            "jpg",
            "jpeg",
            "gif",
            "webp",
            "rar",
            "tar",
            "gz",
            "txt",
            "csv",
            "json",
        ]
        if extension not in allowed_extensions:
            return JsonResponse(
                {"success": False, "message": "Invalid file type."}, status=422
            )

        qr_files_service.replace_qr_file(
            qr_file, uploaded_file, original_name, extension
        )

        return JsonResponse(
            {
                "success": True,
                "message": "File replaced successfully! The QR Code link remains unchanged.",
            }
        )

    return JsonResponse(
        {"success": False, "message": "Invalid request method"}, status=405
    )


@require_POST
def qr_files_destroy(request, id):
    admin_id = _get_admin_from_session(request)
    if not admin_id:
        return redirect("admin_login")

    qr_file = get_object_or_404(QrFile, id=id)

    qr_files_service.delete_qr_file(qr_file)
    from django.contrib import messages

    messages.success(request, "File deleted successfully!")
    return redirect("admin_qr_files_index")


def qr_files_download(request, code):
    try:
        qr_file = QrFile.objects.get(unique_code=code)
    except QrFile.DoesNotExist:
        raise Http404("File not found.")

    qr_files_service.increment_download_count(qr_file)

    file_path = os.path.join(settings.MEDIA_ROOT, qr_file.file_path)
    if os.path.exists(file_path):
        response = FileResponse(
            open(file_path, "rb"), as_attachment=True, filename=qr_file.original_name
        )
        if qr_file.file_type.lower() == "apk" or qr_file.original_name.lower().endswith(
            ".apk"
        ):
            response["Content-Type"] = "application/vnd.android.package-archive"
        return response

    raise Http404("File not found on storage.")
