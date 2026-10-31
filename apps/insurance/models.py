from django.db import models
from django.contrib.auth.models import User

class InsuranceProfile(models.Model):
    SUB_ROLE_CHOICES = (
        ('manager', 'Manager'),
        ('onboarding', 'Onboarding'),
        ('sales', 'Sales'),
        ('accounts', 'Accounts'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='insurance_profile')
    insurance_parent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_users')
    insurance_sub_role = models.CharField(max_length=50, choices=SUB_ROLE_CHOICES, null=True, blank=True)

    def is_insurance_manager(self):
        return self.insurance_sub_role == 'manager' or self.insurance_sub_role is None

    def is_insurance_onboarding(self):
        return self.insurance_sub_role == 'onboarding'

    def is_insurance_sales(self):
        return self.insurance_sub_role == 'sales'

    def is_insurance_accounts(self):
        return self.insurance_sub_role == 'accounts'

    def get_insurance_company_id(self):
        return self.insurance_parent_id if self.insurance_parent_id else self.user.id

    def __str__(self):
        return f"{self.user.username} - {self.insurance_sub_role or 'Company Admin'}"


class InsuranceBulkOrder(models.Model):
    """A bulk-cart Razorpay order and the agents it pays for.

    The cart lives here (not only in the session) so the webhook and
    recover_orphaned_payments can fulfil it if the browser tab closes.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )

    razorpay_order_id = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='insurance_bulk_orders')
    company_id = models.IntegerField()
    cart = models.JSONField(default=list)
    amount_paise = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    razorpay_payment_id = models.CharField(max_length=100, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'insurance_bulk_orders'

    def __str__(self):
        return f"{self.razorpay_order_id} ({self.status})"



