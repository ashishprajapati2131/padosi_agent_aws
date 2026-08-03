import urllib.request
import urllib.error
import ssl
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def test_url(url, expect_header=None):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx) as response:
            status = response.status
            headers = dict(response.headers)
            print(f"URL: {url} -> Status: {status}")
            if expect_header:
                print(f"Header {expect_header}: {headers.get(expect_header)}")
    except urllib.error.HTTPError as e:
        headers = dict(e.headers)
        print(f"URL: {url} -> Status: {e.code}")
        if expect_header:
            print(f"Header {expect_header}: {headers.get(expect_header)}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")

print("--- Testing /robots.txt ---")
test_url('http://127.0.0.1:1234/robots.txt')

print("\n--- Testing /sitemap.xml ---")
test_url('http://127.0.0.1:1234/sitemap.xml')

print("\n--- Testing /django-admin/ ---")
test_url('http://127.0.0.1:1234/django-admin/', 'X-Robots-Tag')
