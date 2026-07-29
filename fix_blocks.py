import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

# We want to match: {% block page-title', 'Sub-Users Management %}
# And replace with: {% block page-title %}Sub-Users Management{% endblock %}
# Also handle: {% block title', $agent->fullname . ' — Insurance Portal %}
# For the $agent->fullname one, it's safer to just wrap it:
# {% block title %}{{ agent.fullname }} — Insurance Portal{% endblock %}

def fix_blocks(content):
    # Fix the standard ones like {% block title', 'Some string %}
    content = re.sub(r'\{%\s*block\s+([a-zA-Z0-9_-]+)\',\s*\'([^\'%]+)\s*%\}', r'{% block \1 %}\2{% endblock %}', content)
    
    # Fix the edge case with $agent->fullname
    # {% block title', $agent->fullname . ' — Insurance Portal %}
    # We will just replace it manually because it's only one case:
    content = content.replace(
        "{% block title', $agent->fullname . ' — Insurance Portal %}",
        "{% block title %}{{ agent.fullname }} — Insurance Portal{% endblock %}"
    )
    
    # Fix base.html yield with default: {% block title', 'Insurance Portal — PadosiAgent %}{% endblock %}
    # Should be: {% block title %}Insurance Portal — PadosiAgent{% endblock %}
    content = re.sub(r'\{%\s*block\s+([a-zA-Z0-9_-]+)\',\s*\'([^\'%]+)\s*%\}\{%\s*endblock\s*%\}', r'{% block \1 %}\2{% endblock %}', content)
    
    # Just in case, remove any remaining ', '
    def generic_fix(match):
        block_name = match.group(1)
        rest = match.group(2).strip()
        # remove trailing quotes if present
        if rest.endswith("'") or rest.endswith('"'):
            rest = rest[:-1]
        return f"{{% block {block_name} %}}{rest}{{% endblock %}}"

    content = re.sub(r'\{%\s*block\s+([a-zA-Z0-9_-]+)\',\s*\'?(.+?)\s*%\}', generic_fix, content)
    
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_blocks(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed blocks in {path}")

print("Done")
