from django.apps import AppConfig


class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agents'
    verbose_name = 'Agent Registration'

    def ready(self):
        from django.contrib.auth.models import User
        
        def get_user_role(self):
            if self.is_superuser or self.is_staff:
                return 'admin'
            if hasattr(self, 'insurance_profile'):
                return 'insurance_company'
            from apps.agents.models import Agent
            if Agent.objects.filter(user=self).exists():
                return 'agent'
            return 'client'
            
        User.add_to_class('role', property(get_user_role))

