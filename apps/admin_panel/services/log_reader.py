"""Parse django.log into entries and grouped issues for the admin System Logs page."""
import re
from datetime import datetime

# [2026-08-08 19:40:39,000] INFO apps.module — message
ENTRY_RE = re.compile(r'^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:,\d+)?\]\s+(\w+)\s+(\S+)\s+(?:—|-)\s?(.*)')
ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
FRAME_RE = re.compile(r'^\s*File "(.+?)", line (\d+), in (.+)$')
EXC_RE = re.compile(r'^([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning|DoesNotExist|NotFound|Denied)\w*)(?::\s?(.*))?$')
HTTP_RE = re.compile(r'^(Not Found|Forbidden|Bad Request|Unauthorized|Method Not Allowed|Gone|Unprocessable Entity|'
                     r'Too Many Requests|Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout): (\S+)')

HTTP_STATUS = {
    'Bad Request': 400, 'Unauthorized': 401, 'Forbidden': 403, 'Not Found': 404, 'Method Not Allowed': 405,
    'Gone': 410, 'Unprocessable Entity': 422, 'Too Many Requests': 429, 'Internal Server Error': 500,
    'Bad Gateway': 502, 'Service Unavailable': 503, 'Gateway Timeout': 504,
}

# Plain-language hints, matched in order against "<exception type> <message>"
HINTS = [
    (r'\b404\b|Not Found:', 'Someone opened a URL that does not exist (broken link, old URL, or a bot scanning). Usually safe to ignore unless it is a page that should exist.'),
    (r'Too Many Requests', 'Rate limit hit: the same visitor sent too many requests in a short time. Normal protection; check only if real users complain.'),
    (r'Forbidden:', 'Access was refused (missing permission or failed CSRF check).'),
    (r'Unprocessable Entity:', 'A form or API call was submitted with invalid data and was rejected by validation.'),
    (r'Service Unavailable:', 'The endpoint deliberately returned 503 (often so the caller retries later, e.g. Razorpay webhooks).'),
    (r'Internal Server Error:', 'The page crashed for the visitor (HTTP 500). Look at the traceback to see which line failed.'),
    (r'OperationalError|ProgrammingError', 'Database query failed: bad SQL, a missing table/column, or the database is unreachable. Check pending migrations.'),
    (r'IntegrityError', 'Database rejected the save: duplicate value or a missing required/related row.'),
    (r'DoesNotExist', 'Code looked up a database record that does not exist (wrong id or deleted row).'),
    (r'TemplateSyntaxError|TemplateDoesNotExist|VariableDoesNotExist', 'A template is broken or missing.'),
    (r'KeyError', 'Code read a dict key that was not there, often missing form/JSON field or setting.'),
    (r'AttributeError', 'Code used an attribute on the wrong kind of object; frequently a value that was None.'),
    (r'TypeError|ValueError', 'A function got a value of the wrong type or format.'),
    (r'ConnectionError|Max retries exceeded|Timeout|timed out|ConnectionRefused', 'Could not reach an external service (network down, wrong host/port, or service not running).'),
    (r'BREVO_API_KEY|MAIL_|email delivery', 'Email could not be sent; check the Brevo API key and MAIL_* settings in .env.'),
    (r'[Rr]azorpay', 'Payment gateway issue; check the order in the Razorpay dashboard and the Payment Reconcile page.'),
]
HINTS = [(re.compile(p), h) for p, h in HINTS]

_NORMALIZE = [
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '<email>'),
    (re.compile(r'\b(order|pay|sub|plan)_[A-Za-z0-9]+'), r'\1_<id>'),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "'…'"),
    (re.compile(r'0x[0-9a-fA-F]+'), '<addr>'),
    (re.compile(r'\d+'), '#'),
]


def _normalize(text):
    for pattern, repl in _NORMALIZE:
        text = pattern.sub(repl, text)
    return text[:200]


def read_tail(path, max_bytes=3 * 1024 * 1024):
    """Last ``max_bytes`` of the log, starting at a whole line."""
    with open(path, 'rb') as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(size - max_bytes, 0))
        data = f.read()
    if size > max_bytes:
        data = data.split(b'\n', 1)[-1]
    return data.decode('utf-8', errors='replace')


def _analyse_trace(lines, base_dir):
    """Frames, exception type/message and the deepest project frame from traceback lines."""
    frames, exc_type, exc_msg = [], '', ''
    base = str(base_dir).replace('\\', '/').rstrip('/') + '/'
    i = 0
    while i < len(lines):
        m = FRAME_RE.match(lines[i])
        if m:
            path = m.group(1).replace('\\', '/')
            code = ''
            if i + 1 < len(lines) and not FRAME_RE.match(lines[i + 1]) and lines[i + 1].startswith('    '):
                code = lines[i + 1].strip()
                i += 1
            is_app = path.startswith(base) and '/site-packages/' not in path and '/.venv/' not in path
            frames.append({
                'file': path[len(base):] if is_app else path.rsplit('/site-packages/', 1)[-1],
                'line': m.group(2), 'func': m.group(3), 'code': code, 'is_app': is_app,
            })
        else:
            e = EXC_RE.match(lines[i].strip()) if not lines[i].startswith(' ') else None
            if e:
                # Keep the last one: chained tracebacks end with the exception that actually surfaced
                exc_type, exc_msg = e.group(1), (e.group(2) or '').strip()
        i += 1
    app_frames = [f for f in frames if f['is_app']]
    return frames, exc_type, exc_msg, (app_frames[-1] if app_frames else (frames[-1] if frames else None))


def parse_entries(text, base_dir):
    entries, current, extra = [], None, []

    def flush():
        if not current:
            return
        stack = [l for l in extra if not set(l.strip()) <= set('^~ ')]
        frames, exc_type, exc_msg, location = _analyse_trace(stack, base_dir)
        current.update(stack='\n'.join(stack), frames=frames, exc_type=exc_type, exc_msg=exc_msg, location=location)
        entries.append(current)

    for raw in text.splitlines():
        line = ANSI_RE.sub('', raw.rstrip())
        m = ENTRY_RE.match(line)
        if m:
            flush()
            extra = []
            try:
                ts = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
            except ValueError:
                ts = None
            current = {'time': ts, 'level': m.group(2).upper(), 'source': m.group(3), 'message': m.group(4)}
        elif current and line.strip():
            extra.append(line)
    flush()

    for e in entries:
        level = e['level']
        e['severity'] = 'error' if level in ('ERROR', 'CRITICAL') else level.lower()
        http = HTTP_RE.match(e['message'])
        e['http_status'] = HTTP_STATUS.get(http.group(1)) if http else None
        e['http_path'] = http.group(2) if http else ''
        if e['exc_type']:
            e['title'] = e['exc_type'].rsplit('.', 1)[-1] + (f": {e['exc_msg']}" if e['exc_msg'] else '')
        else:
            e['title'] = e['message']
        haystack = f"{e['exc_type']} {e['message']} {e['exc_msg']} {e['source']}"
        e['hint'] = next((h for p, h in HINTS if p.search(haystack)), '')
        e['fingerprint'] = '|'.join([
            e['severity'], e['source'], e['exc_type'],
            f"{e['location']['file']}:{e['location']['line']}" if e['location'] else '',
            # 4xx from many different URLs (bots, old links) is one issue; 5xx stays per path
            str(e['http_status']) if e['http_status'] and e['http_status'] < 500 else _normalize(e['message']),
        ])
    return entries


def group_issues(entries):
    """Collapse repeated entries into issues, newest activity first. ``entries`` must be oldest-first."""
    issues = {}
    for e in entries:
        issue = issues.get(e['fingerprint'])
        if issue is None:
            issues[e['fingerprint']] = {'latest': e, 'count': 1, 'first_seen': e['time'], 'last_seen': e['time']}
        else:
            issue['count'] += 1
            issue['latest'] = e
            issue['last_seen'] = e['time']
    order = {'error': 0, 'warning': 1}
    return sorted(issues.values(),
                  key=lambda i: (i['last_seen'] or datetime.min, -order.get(i['latest']['severity'], 2)),
                  reverse=True)
