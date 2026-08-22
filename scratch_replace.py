import re
filepath = 'templates/agents/edit_profile.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

replacement = """        if (!step3Locked) {
            if (!planPermissions.portfolio) lockSection($('#step-3'), "Product Portfolio");
            if (!planPermissions.companies) lockSection($('#portfolio-content'), "Company Portfolio");
        }"""

content = re.sub(
    r'if \(\!step3Locked\) \{[\s\S]*?if \(\!planPermissions\.companies\) lockSection\(\$\(\'#portfolio-content\'\), "Company Portfolio"\);\s*\}',
    replacement,
    content
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
print("Regex Replaced successfully!")
