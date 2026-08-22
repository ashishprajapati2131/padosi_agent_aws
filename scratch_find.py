import re
content = open('templates/agents/edit_profile.html', 'r', encoding='utf-8').read()
idx = content.find('lead-new-business')
matches = list(re.finditer(r'<div class="form-step"[^>]*id="([^"]+)"', content[:idx]))
if matches:
    print(matches[-1].group(1))
