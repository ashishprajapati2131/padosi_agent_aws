import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_syntax(content):
    # Fix {% if ... ) -> {% if ... %}
    # Regex: find {% if [^%}]+ \) and replace \) with %}
    content = re.sub(r'\{%\s*if\s+([^%\}]+?)\)', r'{% if \1 %}', content)
    content = re.sub(r'\{%\s*elif\s+([^%\}]+?)\)', r'{% elif \1 %}', content)

    # Fix request('key') -> request.GET.key
    content = re.sub(r"request\(['\"]([^'\"]+)['\"]\)", r"request.GET.\1", content)
    
    # Fix request('key', 'default') -> request.GET.key|default:'default'
    content = re.sub(r"request\(['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\)", r"request.GET.\1|default:'\2'", content)
    
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_syntax(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed syntax in {path}")

print("Done")
