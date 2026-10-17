from django.db import models
from django.utils import timezone

class AdminActivityLog(models.Model):
    admin_id = models.IntegerField(null=True, blank=True)
    action = models.CharField(max_length=255)
    model_type = models.CharField(max_length=100, null=True, blank=True)
    model_id = models.IntegerField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'admin_activity_logs'

    def __str__(self):
        return f"{self.action} by Admin {self.admin_id} on {self.created_at}"

    @classmethod
    def log(cls, action, model_type=None, model_id=None, details=None, request=None, admin_id=None, severity="INFO", snapshot=None):
        """Write an advanced audit row with comprehensive tracking metadata.
        Never raises: logging must not break the critical user action.

        Automatically captures:
        - Admin ID, Name, and Email
        - IP Address & User-Agent (browser/device)
        - HTTP Request Path & Method
        - Severity level (INFO, WARNING, CRITICAL, EMERGENCY)
        - Entity snapshot (full record data for deletes and edits)
        """
        import logging
        from django.db import connection, transaction

        ip = None
        user_agent = None
        req_path = None
        req_method = None
        admin_email = None
        admin_name = None

        if request is not None:
            try:
                from apps.admin_panel.middleware import ThreatMonitorMiddleware
                ip = ThreatMonitorMiddleware.get_client_ip(request) or None
            except Exception:
                ip = request.META.get('REMOTE_ADDR')
            
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            req_path = getattr(request, 'path', '')
            req_method = getattr(request, 'method', '')

            if admin_id is None:
                try:
                    from apps.admin_panel.views.dashboard import _get_admin_from_session
                    admin_id = _get_admin_from_session(request)
                except Exception:
                    admin_id = None
                if admin_id is None and hasattr(request, 'session'):
                    admin_id = request.session.get('admin_id')

            if hasattr(request, 'session'):
                admin_name = request.session.get('admin_name')
                admin_email = request.session.get('admin_email')

        if isinstance(admin_id, dict):
            admin_id = admin_id.get('id')
        try:
            admin_id = int(admin_id) if admin_id is not None else None
        except (TypeError, ValueError):
            admin_id = None

        # Resolve admin name and email from DB if not in session
        if admin_id and not (admin_name and admin_email):
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT name, email FROM admins WHERE id = %s", [admin_id])
                    row = cursor.fetchone()
                    if row:
                        admin_name = admin_name or row[0]
                        admin_email = admin_email or row[1]
            except Exception:
                pass

        # Build advanced structured details payload
        structured_details = {
            "severity": severity,
            "admin_name": admin_name or "System / Unknown",
            "admin_email": admin_email or "N/A",
            "ip_address": ip,
            "user_agent": user_agent,
            "path": req_path,
            "method": req_method,
            "timestamp": timezone.now().isoformat(),
        }

        if isinstance(details, dict):
            structured_details.update(details)
        elif details:
            structured_details["message"] = str(details)

        if snapshot:
            structured_details["snapshot"] = snapshot

        try:
            with transaction.atomic():
                return cls.objects.create(
                    admin_id=admin_id,
                    action=action,
                    model_type=model_type,
                    model_id=model_id,
                    details=structured_details,
                    ip_address=ip,
                )
        except Exception as orm_err:
            try:
                import json
                with transaction.atomic(), connection.cursor() as cursor:
                    raw_description = f"[{severity}] {action}: {json.dumps(structured_details)}"
                    cursor.execute(
                        "INSERT INTO admin_activity_logs (admin_id, description, model_type, model_id, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        [admin_id, str(raw_description)[:1000], model_type, model_id, timezone.now(), timezone.now()],
                    )
            except Exception as raw_err:
                logging.getLogger(__name__).warning(
                    'Admin activity log failed (%s / %s): %s', orm_err, raw_err, action,
                )
            return None
