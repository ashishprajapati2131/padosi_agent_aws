import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_auth(content):
    # Fix the broken {% if auth( %}->user()->... )
    
    # Manager
    content = content.replace("{% if auth( %}->user()->isInsuranceManager())", "{% if request.user.insurance_profile.is_insurance_manager %}")
    content = content.replace("{% elif auth( %}->user()->isInsuranceManager())", "{% elif request.user.insurance_profile.is_insurance_manager %}")
    content = content.replace("auth()->user()->isInsuranceManager()", "request.user.insurance_profile.is_insurance_manager")
    
    # Onboarding
    content = content.replace("{% if auth( %}->user()->isInsuranceOnboarding())", "{% if request.user.insurance_profile.is_insurance_onboarding %}")
    content = content.replace("{% elif auth( %}->user()->isInsuranceOnboarding())", "{% elif request.user.insurance_profile.is_insurance_onboarding %}")
    content = content.replace("auth()->user()->isInsuranceOnboarding()", "request.user.insurance_profile.is_insurance_onboarding")
    
    # Sales
    content = content.replace("{% if auth( %}->user()->isInsuranceSales())", "{% if request.user.insurance_profile.is_insurance_sales %}")
    content = content.replace("{% elif auth( %}->user()->isInsuranceSales())", "{% elif request.user.insurance_profile.is_insurance_sales %}")
    content = content.replace("auth()->user()->isInsuranceSales()", "request.user.insurance_profile.is_insurance_sales")
    
    # Accounts
    content = content.replace("{% if auth( %}->user()->isInsuranceAccounts())", "{% if request.user.insurance_profile.is_insurance_accounts %}")
    content = content.replace("{% elif auth( %}->user()->isInsuranceAccounts())", "{% elif request.user.insurance_profile.is_insurance_accounts %}")
    content = content.replace("auth()->user()->isInsuranceAccounts()", "request.user.insurance_profile.is_insurance_accounts")
    
    # Fix specific compound if statements
    content = content.replace("{% if request.user.insurance_profile.is_insurance_manager && isset($pendingManagerApprovals))", "{% if request.user.insurance_profile.is_insurance_manager and pendingManagerApprovals %}")
    content = content.replace("{% if request.user.insurance_profile.is_insurance_Accounts && isset($pendingPayments))", "{% if request.user.insurance_profile.is_insurance_accounts and pendingPayments %}")
    content = content.replace("&& isset($pendingManagerApprovals))", "and pendingManagerApprovals %}")
    content = content.replace("&& isset($pendingPayments))", "and pendingPayments %}")
    content = content.replace("&&", "and")
    content = content.replace("||", "or")
    content = content.replace("!", "not ")
    
    # Fullname
    content = content.replace("{{ auth()->user()->fullname }}", "{{ request.user.first_name }}")
    content = content.replace("{{ strtoupper(substr(auth()->user()->fullname ?? 'I', 0, 1)) }}", "{{ request.user.first_name|first|upper }}")
    
    # Fix broken search if
    content = content.replace("{% if request('search' %} or (not request.user.insurance_profile.is_insurance_sales and request('status') and request('status') !== 'all'))", "{% if request.GET.search or not request.user.insurance_profile.is_insurance_sales %}")
    
    # Any residual {% if auth( %}
    content = re.sub(r'\{%\s*if\s+auth\(\s*%\}->user\(\)->is([a-zA-Z]+)\(\)\)', lambda m: f"{{% if request.user.insurance_profile.is_insurance_{m.group(1).lower()} %}}", content)
    
    # Fix PHP array/object access from $agent->fullname or $agent.fullname
    content = re.sub(r'\$([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)', r'\1.\2', content)
    content = re.sub(r'\$([a-zA-Z0-9_]+)', r'\1', content)
    
    # isset in templates
    content = re.sub(r'isset\((.+?)\)', r'\1', content)
    
    # count()
    content = re.sub(r'count\((.+?)\)', r'\1|length', content)
    content = re.sub(r'(.+?)\.count\(\)', r'\1|length', content)
    
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_auth(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed auth logic in {path}")

print("Done")
