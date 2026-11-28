from django.db import models


class PrivacyPolicy(models.Model):
    """One version of the public privacy policy. The published row is what /privacy/ shows."""

    title = models.CharField(max_length=255, default="Privacy Policy")
    effective_date = models.DateField()
    company_name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    contact_email = models.EmailField()
    grievance_email = models.EmailField()
    content = models.TextField()
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "privacy_policies"
        ordering = ["-is_published", "-updated_at", "-id"]

    def __str__(self):
        state = "published" if self.is_published else "draft"
        return f"{self.title} ({state})"
