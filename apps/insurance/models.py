from django.db import models
from django.contrib.auth.models import User
from apps.agents.models import Agent

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



