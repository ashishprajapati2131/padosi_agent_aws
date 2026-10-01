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
    def log(cls, action, model_type=None, model_id=None, details=None, request=None, admin_id=None):
        """Write an audit row. Never raises: logging must not break the action.

        The admin comes from the admin session token (session['admin_id'] was
        never set, so every row had a NULL admin). The table may still have the
        legacy Laravel layout (description/updated_at), so a failed ORM insert
        falls back to that layout.
        """
        import logging
        from django.db import connection, transaction

        ip = None
        if request is not None:
            try:
                from apps.admin_panel.middleware import ThreatMonitorMiddleware
                ip = ThreatMonitorMiddleware.get_client_ip(request) or None
            except Exception:
                ip = request.META.get('REMOTE_ADDR')
            if admin_id is None:
                try:
                    from apps.admin_panel.views.dashboard import _get_admin_from_session
                    admin_id = _get_admin_from_session(request)
                except Exception:
                    admin_id = None
                if admin_id is None and hasattr(request, 'session'):
                    admin_id = request.session.get('admin_id')
        if isinstance(admin_id, dict):
            admin_id = admin_id.get('id')
        try:
            admin_id = int(admin_id) if admin_id is not None else None
        except (TypeError, ValueError):
            admin_id = None

        try:
            with transaction.atomic():
                return cls.objects.create(
                    admin_id=admin_id,
                    action=action,
                    model_type=model_type,
                    model_id=model_id,
                    details=details,
                    ip_address=ip,
                )
        except Exception as orm_err:
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    description = action if details in (None, '') else f'{action}: {details}'
                    cursor.execute(
                        "INSERT INTO admin_activity_logs (admin_id, description, model_type, model_id, created_at, updated_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        [admin_id, str(description)[:1000], model_type, model_id, timezone.now(), timezone.now()],
                    )
            except Exception as raw_err:
                logging.getLogger(__name__).warning(
                    'Admin activity log failed (%s / %s): %s', orm_err, raw_err, action,
                )
            return None
