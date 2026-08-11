import re

log_path = 'c:/Users/DELL/Downloads/7_22_2026/src/media/logs/django.log'
log_pattern = re.compile(r'^\[(.*?)\]\s+(\w+)\s+(\S+)\s+(?:—|-|.*?)\s+(.*)')
ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

with open(log_path, 'r', encoding='utf-8') as f:
    for _ in range(100):
        line = f.readline().rstrip('\n')
        if not line: continue
        line = ansi_escape.sub('', line)
        match = log_pattern.match(line)
        print(f"Match: {bool(match)}")
        if match:
            print(f"Timestamp: {match.group(1)}, Level: {match.group(2)}, Env: {match.group(3)}, Message: {match.group(4)}")
