import re

with open('apps/agents/services/feature_unlock.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all PLAN_SLUGS with get_plan_slugs()
content = content.replace('PLAN_SLUGS', 'get_plan_slugs()')

with open('apps/agents/services/feature_unlock.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced PLAN_SLUGS with get_plan_slugs()")
