import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
django.setup()

from django.contrib.auth.models import User
from apps.insurance.models import InsuranceProfile

def create_manager():
    email = "manager@gmail.com"
    password = "password"
    
    # Check if user exists, create or update
    user, created = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': 'Insurance', 'last_name': 'Manager'})
    
    # Set the exact password requested
    user.set_password(password)
    user.save()
    
    # Ensure the user has an InsuranceProfile with the 'manager' role
    profile, p_created = InsuranceProfile.objects.get_or_create(user=user)
    profile.insurance_sub_role = 'manager'
    
    # We might need to set an insurance_id (self reference or parent reference).
    # Since they are a manager, they are likely the top level insurance company.
    profile.insurance_id = None # or their own ID based on how the system works
    profile.save()
    
    if created:
        print(f"Created new user: {email} with password: {password}")
    else:
        print(f"Updated existing user: {email} with password: {password}")
        
    if p_created:
        print("Created InsuranceProfile with 'manager' role.")
    else:
        print("Updated InsuranceProfile to 'manager' role.")

if __name__ == "__main__":
    create_manager()
