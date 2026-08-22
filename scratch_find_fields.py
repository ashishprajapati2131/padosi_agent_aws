import re
content = open('templates/admin/plans/form.html', 'r', encoding='utf-8').read()
matches = re.findall(r'name="([^"]+)"', content)
for m in matches:
    if 'show' in m or 'edit' in m:
        print(m)
