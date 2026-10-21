"""
Verify the landing-page performance changes (before and after a production deploy).

Usage:
    # 1) Before pushing (local checkout, no DB needed):
    python scripts/verify_landing_perf.py --local

    # 2) After deploy (live site):
    python scripts/verify_landing_perf.py --host https://padosiagent.com

Exit code 0 = all checks passed, 1 = at least one FAIL. WARN lines do not fail the run.
"""

import argparse
import os
import re
import ssl
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UA = 'Mozilla/5.0 (PadosiAgent verify_landing_perf)'

results = {'PASS': 0, 'WARN': 0, 'FAIL': 0}


def report(status, name, detail=''):
    results[status] += 1
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ''))


def check(cond, name, detail='', warn_only=False):
    report('PASS' if cond else ('WARN' if warn_only else 'FAIL'), name, '' if cond else detail)
    return cond


# ─────────────────────────────── local (pre-push) ───────────────────────────────

def run_local():
    print('\n== Local pre-push checks ==')
    proc = subprocess.run([sys.executable, 'manage.py', 'check'], cwd=PROJECT_ROOT,
                          capture_output=True, text=True)
    check(proc.returncode == 0, 'manage.py check', (proc.stdout + proc.stderr)[-500:])

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
    sys.path.insert(0, str(PROJECT_ROOT))
    import django
    django.setup()
    from django.conf import settings
    from django.template import TemplateSyntaxError
    from django.template.loader import get_template

    check('daphne' not in settings.INSTALLED_APPS,
          "'daphne' not loaded outside runserver (saves ~1-2.5s per cold start)")

    # Compile every template so a syntax error anywhere fails here, not in production.
    bad = []
    count = 0
    dirs = [PROJECT_ROOT / 'templates'] + list(PROJECT_ROOT.glob('apps/*/templates'))
    for base in dirs:
        for path in base.rglob('*.html'):
            name = path.relative_to(base).as_posix()
            count += 1
            try:
                get_template(name)
            except TemplateSyntaxError as exc:
                bad.append(f"{name}: {exc}")
            except Exception:
                pass  # missing optional includes etc. are not syntax errors
    check(not bad, f'all {count} templates compile', '; '.join(bad[:5]))

    style = (PROJECT_ROOT / 'static/css/style.css').read_text(encoding='utf-8')
    check(not style.lstrip().startswith('@import'), 'style.css has no render-blocking @import')

    widget = (PROJECT_ROOT / 'static/chatbot/js/widget.js').read_text(encoding='utf-8')
    check('chatbotOnReady' in widget, 'chatbot widget.js can init after DOMContentLoaded')

    home = (PROJECT_ROOT / 'templates/public/home.html').read_text(encoding='utf-8')
    check("{% block jquery_attrs %}defer{% endblock %}" in home, 'home.html defers jQuery')
    check("$(document).ready" not in home, 'home.html has no parse-time $(document).ready')

    from apps.home.services.avatar_thumbs import small_avatar_url
    check(small_avatar_url('https://example.com/a.jpg') == 'https://example.com/a.jpg'
          and small_avatar_url('/media/../manage.py') == '/media/../manage.py',
          'avatar thumbnail helper ignores external / unsafe paths')


# ─────────────────────────────── remote (post-deploy) ───────────────────────────────

def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'identity'})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            first = r.read(1)
            ttfb = time.perf_counter() - t0
            body = first + r.read()
            return r.status, body.decode('utf-8', 'replace'), ttfb, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, '', time.perf_counter() - t0, {}
    except Exception as e:
        return 0, str(e), time.perf_counter() - t0, {}


def script_tags(html, needle):
    return [t for t in re.findall(r'<script\b[^>]*>', html) if needle in t]


def run_remote(host):
    host = host.rstrip('/')
    print(f'\n== Live checks: {host} ==')

    status, html, _, headers = fetch(host + '/')
    if not check(status == 200, 'GET / returns 200', f'got {status}'):
        return

    # TTFB sample (first one may be a cold start; that is exactly what we want to see).
    ttfbs = [fetch(f"{host}/?_v={i}{int(time.time())}")[2] for i in range(6)]
    med = statistics.median(ttfbs)
    print(f"  [INFO] TTFB samples: {', '.join(f'{t:.2f}s' for t in ttfbs)} (median {med:.2f}s)")
    check(med < 1.5, 'median TTFB under 1.5s', f'median {med:.2f}s', warn_only=True)

    # 1. Preloader
    check(re.search(r'class="loader-mask"[^>]*style="display:none"', html) is not None,
          'preloader overlay hidden on first paint')

    # 2. jQuery deferred on home
    jq = script_tags(html, 'jquery-3.7.1')
    check(len(jq) == 1 and 'defer' in jq[0], 'jQuery is deferred on home', str(jq))

    # 3. No duplicate owl.carousel / synchronous plugin scripts
    owl = script_tags(html, 'owl.carousel')
    check(len(owl) == 1 and 'defer' in owl[0], 'owl.carousel.js loaded once, deferred', str(owl))
    for lib in ('aos', 'animation'):
        tags = [t for t in script_tags(html, f'/js/{lib}') if '.js' in t]
        check(tags and all('defer' in t for t in tags), f'{lib}.js deferred', str(tags))
    check(html.count('owl.carousel.min') == 1, 'owl CSS linked once')

    # 4. Avatars: small thumbnails + lazy
    m = re.search(r'var reviewsData = (\[.*?\]);', html, re.S)
    if m:
        big = re.findall(r'/media/(?!thumbs/)[^"\s]+\.(?:png|jpe?g)', m.group(1), re.I)
        check(not big, 'testimonial avatars use /media/thumbs/ WebP',
              f'{len(big)} full-size photos still listed (cache may still be warm; clear cache or wait 30 min)',
              warn_only=True)
        thumbs = re.findall(r'(/media/thumbs/[^"\s]+\.webp)', m.group(1))
        if thumbs:
            t_status, t_body, _, _ = fetch(host + thumbs[0])
            check(t_status == 200, 'avatar thumbnail is served', f'{thumbs[0]} -> {t_status}')
    check('class="review-avatar" width="40" height="40" loading="lazy"' in html,
          'review avatar <img> is lazy with fixed size')

    # 5. Hero LCP preload
    pre = re.search(r'<link rel="preload" as="image" href="([^"]+)"[^>]*fetchpriority="high"', html)
    if check(pre is not None, 'hero image preloaded with fetchpriority=high'):
        check(fetch(host + pre.group(1))[0] == 200, 'preloaded hero image returns 200', pre.group(1))
    check('fetchpriority="high" width="1536" height="1024"' in html, 'hero <img> has fetchpriority + size')

    # 6. CSS / fonts
    check(re.search(r'<link href="https://fonts\.googleapis\.com/css2\?family=Outfit[^"]*family=Jost[^"]*family=Urbanist', html)
          is not None, 'Outfit + Jost + Urbanist in one fonts <link>')
    css = re.search(r'href="([^"]*/css/style[^"]*\.css)"', html)
    if css:
        _, css_body, _, _ = fetch(host + css.group(1))
        check(bool(css_body) and not css_body.lstrip().startswith('@import'),
              'deployed style.css has no @import (collectstatic ran)')
    check(re.search(r'font-awesome[^"]*all\.min\.css"[^>]*media="print"', html) is not None,
          'Font Awesome loads without blocking render')
    check(re.search(r'magnific-popup[^"]*"[^>]*media="print"', html) is not None,
          'magnific-popup.css loads without blocking render')
    check(re.search(r'agent-profile-view[^"]*"[^>]*media="print"', html) is not None,
          'agent-profile-view.css non-blocking on home')

    # 7. Chatbot lazy-load
    check(not script_tags(html, 'chatbot/js/widget'), 'chatbot widget.js not loaded as a blocking <script>')
    w = re.search(r'var src = "([^"]*chatbot/js/widget[^"]*)"', html)
    if check(w is not None, 'chatbot lazy loader present'):
        w_status, w_body, _, _ = fetch(host + w.group(1))
        check(w_status == 200 and 'chatbotOnReady' in w_body, 'deployed widget.js has lazy-init guard',
              f'status {w_status}')
    check(fetch(host + '/chatbot-api/chips/')[0] == 200, '/chatbot-api/chips/ still works')

    # 8. Other pages unchanged: jQuery must stay synchronous there (their inline JS needs $ at parse time).
    for path in ('/about/', '/faq/', '/contact/', '/find-agents/'):
        p_status, p_html, _, _ = fetch(host + path)
        if not check(p_status == 200, f'GET {path} returns 200', f'got {p_status}'):
            continue
        p_jq = script_tags(p_html, 'jquery-3.7.1')
        check(len(p_jq) == 1 and 'defer' not in p_jq[0], f'{path}: jQuery still loads synchronously', str(p_jq))
        check('agent-profile-view' in p_html, f'{path}: agent-profile-view.css still linked')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--local', action='store_true', help='run pre-push checks on this checkout')
    ap.add_argument('--host', help='run live checks against this base URL')
    args = ap.parse_args()
    if not args.local and not args.host:
        ap.error('pass --local and/or --host URL')

    if args.local:
        run_local()
    if args.host:
        run_remote(args.host)

    print(f"\nResult: {results['PASS']} passed, {results['WARN']} warnings, {results['FAIL']} failed")
    sys.exit(1 if results['FAIL'] else 0)


if __name__ == '__main__':
    main()
