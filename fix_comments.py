import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def fix_comments(content):
    # The regex looks for <not -- then anything lazily until -.
    # We replace it with {# ... #} which is the django template comment,
    # or <!-- ... --> for HTML comment. Let's use {# ... #} so it doesn't even render in HTML.
    new_content = re.sub(r'<not --(.*?)-\.', r'{# \1 #}', content, flags=re.DOTALL)
    
    # Also just in case there's any stray <not -- without -.
    # We can't really do much but the regex above should catch the pattern perfectly
    # because they were generated in pairs.
    return new_content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_comments(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed comments in {path}")

print("Done")
