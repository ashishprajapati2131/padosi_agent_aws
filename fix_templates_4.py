import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_file(path, func):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = func(content)
    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Fixed {path}")

# 1. agents/create.html
path1 = os.path.join(tpl_dir, "agents", "create.html")
if os.path.exists(path1):
    def fix_create(c):
        c = c.replace("{{ date('Y-m-d') }}", '{% now "Y-m-d" %}')
        return c
    fix_file(path1, fix_create)

# 2. approvals/index.html and payments/index.html
def fix_has_pages(c):
    return c.replace("{% if agents.hasPages( %})", "{% if agents.has_other_pages %}")
for p in ["approvals/index.html", "payments/index.html"]:
    path_ = os.path.join(tpl_dir, p)
    if os.path.exists(path_):
        fix_file(path_, fix_has_pages)

# 3. notify.html
path_notify = os.path.join(tpl_dir, "notify.html")
if os.path.exists(path_notify):
    def fix_notify(c):
        c = c.replace("<option value=\"{% if agent.id }}\" {{ old('agent_id') == agent.id %}'selected'{% else %}''{% endif %}>", 
                      '<option value="{{ agent.id }}" {% if request.POST.agent_id == agent.id|stringformat:"s" %}selected{% endif %}>')
        c = c.replace("{{ pushAgents.) }}|length", "{{ pushAgents|length }}")
        c = c.replace("{{ old('title') }}", "{{ request.POST.title|default_if_none:'' }}")
        c = c.replace("{{ old('body') }}", "{{ request.POST.body|default_if_none:'' }}")
        return c
    fix_file(path_notify, fix_notify)

# 4. subusers/index.html
path_sub = os.path.join(tpl_dir, "subusers", "index.html")
if os.path.exists(path_sub):
    def fix_sub(c):
        c = c.replace("roleInfo['color']", "roleInfo.color")
        c = c.replace("roleInfo['icon']", "roleInfo.icon")
        c = c.replace("roleInfo['title']", "roleInfo.title")
        c = c.replace("roleInfo['desc']", "roleInfo.desc")
        c = c.replace("@foreach(roles as roleKey => roleInfo)", "{% for roleKey, roleInfo in roles.items %}")
        c = c.replace("@endforeach", "{% endfor %}")
        return c
    fix_file(path_sub, fix_sub)

print("Done")
