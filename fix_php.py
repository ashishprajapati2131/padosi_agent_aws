import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_static(content):
    # Fix {{ {% static '...' %} }} to {% static '...' %}
    # Match {{ {% static 'anything' %} }}
    content = re.sub(r'\{\{\s*(\{% static.+?%\})\s*\}\}', r'\1', content)
    # Match {{ asset('...') }}
    content = re.sub(r"\{\{\s*asset\(['\"](.+?)['\"]\)\s*\}\}", r"{% static '\1' %}", content)
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_static(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed static in {path}")

print("Done")
