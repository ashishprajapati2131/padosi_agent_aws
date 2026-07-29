import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_pagination(content):
    content = content.replace("{{ agents.links() }}", "{% include 'insurance/pagination.html' with page_obj=agents %}")
    content = content.replace("{{ leads.links() }}", "{% include 'insurance/pagination.html' with page_obj=leads %}")
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_pagination(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed pagination in {path}")

print("Done")
