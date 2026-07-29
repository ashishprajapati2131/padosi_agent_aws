import os, re

for root, _, files in os.walk(r'c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance'):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            matches = re.findall(r'{%\s*url\s+[\'"]([^\'"]+)[\'"]', content)
            for m in matches:
                if '.' in m:
                    print(f"{path}: {m}")
