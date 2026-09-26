"""
Automated Production Smoke Test for PadosiAgent.
Usage:
    python scripts/smoke_test.py --host https://padosiagent.com
    python scripts/smoke_test.py --host http://localhost:8000
"""

import sys
import time
import argparse
import urllib.request
import urllib.error
import ssl
import json


def run_smoke_tests(base_url):
    print(f"\n=== PadosiAgent Production Smoke Test Suite ===")
    print(f"Target: {base_url}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    endpoints = [
        ('/health/', 200, 'JSON Health Check'),
        ('/healthz', 200, 'Healthz Alias'),
        ('/', 200, 'Home Page'),
        ('/agent-login/', 200, 'Agent Login Page'),
        ('/sitemap.xml', 200, 'SEO XML Sitemap'),
        ('/manifest.webmanifest', 200, 'PWA Manifest'),
        ('/sw.js', 200, 'PWA Service Worker'),
        ('/offline.html', 200, 'PWA Offline Fallback'),
    ]

    context = ssl.create_default_context()
    passed = 0
    failed = 0

    for path, expected_status, description in endpoints:
        url = base_url.rstrip('/') + path
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'PadosiAgent-SmokeTest/1.0'})
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                status = response.getcode()
                body = response.read(2048)
                duration = round((time.time() - t0) * 1000, 1)

                if status == expected_status:
                    extra = ""
                    if '/health/' in path:
                        try:
                            health_data = json.loads(body.decode('utf-8'))
                            extra = f" [DB: {health_data.get('database')}, Cache: {health_data.get('cache')}]"
                        except Exception:
                            pass
                    print(f"  [OK]   {path:<25} Status: {status} ({duration}ms){extra} - {description}")
                    passed += 1
                else:
                    print(f"  [FAIL] {path:<25} Status: {status} (Expected: {expected_status}) ({duration}ms) - {description}")
                    failed += 1

        except urllib.error.HTTPError as e:
            duration = round((time.time() - t0) * 1000, 1)
            if e.code == expected_status:
                print(f"  [OK]   {path:<25} Status: {e.code} ({duration}ms) - {description}")
                passed += 1
            else:
                print(f"  [FAIL] {path:<25} HTTPError {e.code} ({duration}ms) - {description}")
                failed += 1
        except Exception as e:
            duration = round((time.time() - t0) * 1000, 1)
            print(f"  [FAIL] {path:<25} Network/SSL Error: {e} ({duration}ms) - {description}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"Smoke Test Summary: {passed} Passed, {failed} Failed")
    if failed == 0:
        print("[SUCCESS] All smoke test endpoints verified operational!\n")
        return 0
    else:
        print("[WARNING] One or more smoke tests failed.\n")
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="PadosiAgent Production Smoke Test")
    parser.add_argument('--host', type=str, default='https://padosiagent.com', help='Target host URL')
    args = parser.parse_args()
    sys.exit(run_smoke_tests(args.host))
