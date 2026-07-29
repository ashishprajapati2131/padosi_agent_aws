import os

file_path = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance\base.html"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_nav = """        <nav class="sidebar-nav">
            <div class="nav-section-title">Main</div>
            <ul class="list-unstyled mb-0">
                <li class="nav-item">
                    <a href="{% url 'insurance:dashboard' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:dashboard' %}active{% endif %}">
                        <i class="fas fa-chart-pie"></i> Dashboard
                    </a>
                </li>
                
                {% if request.user.insurance_profile.is_insurance_manager or request.user.insurance_profile.is_insurance_sales %}
                <li class="nav-item">
                    <a href="{% url 'insurance:agents.index' %}"
                        class="{% if 'agents' in request.path and not 'create' in request.path %}active{% endif %}">
                        <i class="fas fa-users"></i> My Agents
                    </a>
                </li>
                {% endif %}
                
                {% if request.user.insurance_profile.is_insurance_onboarding %}
                <li class="nav-item">
                    <a href="{% url 'insurance:agents.index' %}"
                        class="{% if 'agents' in request.path and not 'create' in request.path %}active{% endif %}">
                        <i class="fas fa-list-check"></i> My Onboardings
                    </a>
                </li>
                {% endif %}

                {% if request.user.insurance_profile.is_insurance_accounts %}
                <li class="nav-item">
                    <a href="{% url 'insurance:payments.index' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:payments.index' %}active{% endif %}">
                        <i class="fas fa-file-invoice-dollar"></i> Payments Queue
                    </a>
                </li>
                {% endif %}
            </ul>

            {% if request.user.insurance_profile.is_insurance_manager or request.user.insurance_profile.is_insurance_onboarding or request.user.insurance_profile.is_insurance_sales %}
            <div class="nav-section-title">Actions</div>
            <ul class="list-unstyled mb-0">
                {% if request.user.insurance_profile.is_insurance_manager or request.user.insurance_profile.is_insurance_onboarding %}
                <li class="nav-item">
                    <a href="{% url 'insurance:agents.create' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:agents.create' %}active{% endif %}">
                        <i class="fas fa-user-plus"></i> Onboard Agent
                    </a>
                </li>
                {% endif %}
                
                {% if request.user.insurance_profile.is_insurance_manager %}
                <li class="nav-item">
                    <a href="{% url 'insurance:approvals.index' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:approvals.index' %}active{% endif %}">
                        <i class="fas fa-clipboard-check"></i> Approvals Queue
                    </a>
                </li>
                {% endif %}

                {% if request.user.insurance_profile.is_insurance_manager or request.user.insurance_profile.is_insurance_sales %}
                <li class="nav-item">
                    <a href="{% url 'insurance:notify' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:notify' %}active{% endif %}">
                        <i class="fas fa-bell"></i> Send Notification
                    </a>
                </li>
                {% endif %}
            </ul>
            {% endif %}

            <div class="nav-section-title">Account</div>
            <ul class="list-unstyled mb-0">
                {% if request.user.insurance_profile.is_insurance_manager %}
                <li class="nav-item">
                    <a href="{% url 'insurance:subusers.index' %}"
                        class="{% if 'subusers' in request.path %}active{% endif %}">
                        <i class="fas fa-users-gear"></i> Manage Sub-Users
                    </a>
                </li>
                {% endif %}
                <li class="nav-item">
                    <a href="{% url 'insurance:profile' %}"
                        class="{% if request.resolver_match.view_name == 'insurance:profile' %}active{% endif %}">
                        <i class="fas fa-user-circle"></i> My Profile
                    </a>
                </li>
            </ul>
        </nav>
"""

# Replace lines 512 to 599 with the new nav
new_lines = lines[:511] + [new_nav] + lines[599:]

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Replaced nav bar")
