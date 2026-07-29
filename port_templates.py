import os
import glob
import re
import shutil

src_dir = r"C:\Users\DELL\Downloads\7_22_2026\11_7\resources\views\insurance"
dst_dir = r"C:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

def blade_to_django(content):
    # Base conversions
    content = re.sub(r'@extends\([\'"](.+?)[\'"]\)', r"{% extends '\1.html' %}", content)
    content = re.sub(r'insurance\.layout', 'insurance/base', content) # Specific mapping for layout
    
    # Sections -> Blocks
    content = re.sub(r'@section\([\'"](.+?)[\'"]\)', r"{% block \1 %}", content)
    content = re.sub(r'@endsection', r"{% endblock %}", content)
    content = re.sub(r'@yield\([\'"](.+?)[\'"]\)', r"{% block \1 %}{% endblock %}", content)

    # Includes
    content = re.sub(r'@include\([\'"](.+?)[\'"]\)', lambda m: "{% include '" + m.group(1).replace('.', '/') + ".html' %}", content)

    # PHP Variables: {{ $var }} -> {{ var }}, taking care of objects $var->prop -> var.prop
    content = re.sub(r'\{\{\s*\$([a-zA-Z0-9_]+)->([a-zA-Z0-9_]+)\s*\}\}', r"{{ \1.\2 }}", content)
    content = re.sub(r'\{\{\s*\$([a-zA-Z0-9_]+)\s*\}\}', r"{{ \1 }}", content)

    # Foreach
    content = re.sub(r'@foreach\s*\(\$([a-zA-Z0-9_]+)\s+as\s+\$([a-zA-Z0-9_]+)\)', r"{% for \2 in \1 %}", content)
    content = re.sub(r'@endforeach', r"{% endfor %}", content)

    # If / Else
    content = re.sub(r'@if\s*\((.+?)\)', r"{% if \1 %}", content)
    content = re.sub(r'@elseif\s*\((.+?)\)', r"{% elif \1 %}", content)
    content = re.sub(r'@else', r"{% else %}", content)
    content = re.sub(r'@endif', r"{% endif %}", content)
    
    # Fix if conditions converting PHP variables
    def fix_if_condition(match):
        cond = match.group(1)
        cond = re.sub(r'\$([a-zA-Z0-9_]+)->([a-zA-Z0-9_]+)', r'\1.\2', cond)
        cond = re.sub(r'\$([a-zA-Z0-9_]+)', r'\1', cond)
        return "{% if " + cond + " %}"
    content = re.sub(r'\{%\s*if\s+(.+?)\s*%\}', fix_if_condition, content)

    # Route -> URL
    content = re.sub(r'route\([\'"]([^\'"]+)[\'"]\)', r"{% url '\1' %}", content)
    content = content.replace("insurance.", "insurance:")
    content = re.sub(r'route\([\'"]([^\'"]+)[\'"],\s*\$([a-zA-Z0-9_]+)->id\)', r"{% url '\1' \2.id %}", content)

    # Asset -> Static
    content = re.sub(r'asset\([\'"](.+?)[\'"]\)', r"{% static '\1' %}", content)
    if '{% static' in content and '{% load static %}' not in content:
        content = "{% load static %}\n" + content

    # CSRF
    content = re.sub(r'@csrf', r"{% csrf_token %}", content)
    content = re.sub(r'@method\([\'"](.+?)[\'"]\)', r'<input type="hidden" name="_method" value="\1">', content)

    # Blade unescaped {!! !!} -> {{ |safe }}
    content = re.sub(r'\{!!\s*\$([a-zA-Z0-9_]+)->([a-zA-Z0-9_]+)\s*!!\}', r"{{ \1.\2|safe }}", content)
    content = re.sub(r'\{!!\s*\$([a-zA-Z0-9_]+)\s*!!\}', r"{{ \1|safe }}", content)

    # Errors
    content = re.sub(r'@error\([\'"](.+?)[\'"]\)', r"{% if form.\1.errors %}", content)
    content = re.sub(r'@enderror', r"{% endif %}", content)

    # Empty
    content = re.sub(r'@empty', r"{% empty %}", content)
    content = re.sub(r'@forelse\s*\(\$([a-zA-Z0-9_]+)\s+as\s+\$([a-zA-Z0-9_]+)\)', r"{% for \2 in \1 %}", content)
    content = re.sub(r'@endforelse', r"{% endfor %}", content)

    return content

if not os.path.exists(dst_dir):
    os.makedirs(dst_dir)

for root, _, files in os.walk(src_dir):
    for file in files:
        if file.endswith('.blade.php'):
            src_path = os.path.join(root, file)
            rel_path = os.path.relpath(src_path, src_dir)
            
            # Replace layout.blade.php to base.html
            out_name = rel_path.replace('.blade.php', '.html')
            if out_name == 'layout.html':
                out_name = 'base.html'
                
            dst_path = os.path.join(dst_dir, out_name)
            
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            with open(src_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            converted = blade_to_django(content)
            
            with open(dst_path, 'w', encoding='utf-8') as f:
                f.write(converted)
            print(f"Converted {rel_path} to {out_name}")

print("Done converting templates.")
