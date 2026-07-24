import os
import re
import uuid
import logging
import threading
import queue
import requests
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def validate_url(url):
    """Validates discovered social profile URL."""
    try:
        if not url.startswith("https://"):
            return False
            
        low_url = url.lower()
        # Reject login, search, or signin pages
        if any(term in low_url for term in ["login", "signin", "signup", "search", "register", "auth"]):
            return False
            
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.head(url, headers=headers, allow_redirects=True, timeout=3)
        if res.status_code == 405: # HEAD not allowed
            res = requests.get(url, headers=headers, allow_redirects=True, timeout=3)
            
        return res.status_code < 400
    except Exception:
        return False

def amfi_worker(arn_number, response_q):
    from playwright.sync_api import sync_playwright
    playwright_inst = None
    browser = None
    context = None
    page = None
    start_time = datetime.now()
    
    try:
        # Set WindowsProactorEventLoopPolicy on Windows to support subprocesses in Playwright
        import sys
        import asyncio
        if sys.platform == 'win32':
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception as loop_err:
                logger.error(f"Failed to set event loop policy: {loop_err}")

        # Start a local playwright instance on this thread!
        playwright_inst = sync_playwright().start()
        headless = os.getenv('PLAYWRIGHT_HEADLESS', 'True').lower() in ('true', '1', 'yes')
        browser = playwright_inst.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage", "--no-sandbox"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        # 1. Load AMFI Locate Distributor page
        logger.info(f"AMFI search started for ARN: {arn_number}")
        page.goto("https://www.amfiindia.com/locate-distributor")
        page.wait_for_load_state("networkidle")

        # Check for CAPTCHA/Cloudflare
        body_html = page.content()
        if "cloudflare" in body_html.lower() or "challenge-running" in body_html.lower() or page.locator("iframe[src*='cloudflare']").is_visible():
            response_q.put({
                "status": "ERROR",
                "message": "Verification cannot continue because AMFI requested human verification."
            })
            return

        # 2. Enter ARN and search
        search_input = page.locator("input[placeholder*='Search for ARN Number']").first
        if not search_input.is_visible():
            page.wait_for_selector("input[placeholder*='Search for ARN Number']", timeout=5000)
            
        # Extract digits only to type into AMFI search box (e.g. "68758" instead of "ARN-68758")
        digits_only = re.sub(r'[^\d]', '', arn_number)
        search_input.fill(digits_only)
        page.keyboard.press("Enter")
        
        # Wait for results or empty message
        page.wait_for_timeout(3000)

        # Check if record not found
        body_text = page.locator("body").text_content()
        if "no distributor found" in body_text.lower() or "no records found" in body_text.lower() or "no data found" in body_text.lower():
            response_q.put({
                "status": "ERROR",
                "message": "No distributor found for this ARN."
            })
            return

        # 3. Scrape fields dynamically using robust Mui grid row parser
        soup = BeautifulSoup(page.content(), 'html.parser')
        divs = soup.find_all('div')
        
        headers = []
        parsed_row = {}
        
        # Find the header row
        for d in divs:
            leaves = [leaf.text.strip().replace('\u200b', '') for leaf in d.find_all('div') if len(leaf.find_all('div')) == 0]
            if 'ARN' in leaves and "ARN Holder's Name" in leaves and len(leaves) < 20:
                headers = leaves
                break
                
        if headers:
            for d in divs:
                leaves = [leaf.text.strip().replace('\u200b', '') for leaf in d.find_all('div') if len(leaf.find_all('div')) == 0]
                if len(leaves) == len(headers) and leaves != headers:
                    row_dict = {}
                    for h, val in zip(headers, leaves):
                        if h:
                            row_dict[h] = val
                    
                    arn_val = row_dict.get('ARN', '')
                    if arn_val.isdigit() and int(arn_val) == int(digits_only):
                        parsed_row = row_dict
                        break
                        
        data = {}
        found_data = False
        if parsed_row:
            data = parsed_row
            found_data = True
            
        # Fallback to older table/MuiTypography checks if grid row parser failed
        if not found_data:
            # Fallback table parser
            tables = page.query_selector_all("table")
            for table in tables:
                rows = table.query_selector_all("tr")
                for row in rows:
                    cols = row.query_selector_all("td, th")
                    if len(cols) >= 2:
                        key = cols[0].text_content().strip().rstrip(':').strip()
                        val = cols[1].text_content().strip()
                        if key and val:
                            if "//<![CDATA[" in key or "//<![CDATA[" in val or len(key) > 100:
                                continue
                            data[key] = val
                            found_data = True

            for table in tables:
                headers_fallback = [th.text_content().strip() for th in table.query_selector_all("th")]
                if headers_fallback:
                    rows = table.query_selector_all("tr")
                    for r in rows:
                        tds = r.query_selector_all("td")
                        if len(tds) == len(headers_fallback):
                            for h, td in zip(headers_fallback, tds):
                                key = h
                                val = td.text_content().strip()
                                if key and val:
                                    if "//<![CDATA[" in key or "//<![CDATA[" in val or len(key) > 100:
                                        continue
                                    data[key] = val
                                    found_data = True

            # Fallback to key-value elements
            labels = page.query_selector_all(".MuiTypography-root")
            for lbl in labels:
                text = lbl.text_content().strip()
                if ":" in text:
                    parts = text.split(":", 1)
                    key = parts[0].strip()
                    val = parts[1].strip()
                    if key and val and len(key) < 100 and not "//<![CDATA[" in key:
                        data[key] = val
                        found_data = True

        if not found_data or len(data) < 2:
            response_q.put({
                "status": "ERROR",
                "message": "No distributor found for this ARN."
            })
            return

        # Map dynamic results
        mapped_data = AMFIScraperService.map_fields(data)
        distributor_name = mapped_data.get("distributor_name", "")
        city = mapped_data.get("city", "")
        
        # 4. Social Media Discovery Search
        social_profiles = {
            "linkedin": "",
            "facebook": "",
            "instagram": "",
            "youtube": "",
            "website": "",
            "google_business_profile": ""
        }
        
        if distributor_name:
            query = f'"{distributor_name}" "{city}" linkedin OR facebook OR instagram OR youtube'
            logger.info(f"Social search started for query: {query}")
            try:
                # Open google search
                page.goto(f"https://www.google.com/search?q={requests.utils.quote(query)}")
                page.wait_for_load_state("networkidle", timeout=8000)
                
                # Extract links
                links = page.query_selector_all("a[href]")
                discovered_urls = []
                for link in links:
                    href = link.get_attribute("href")
                    if href and href.startswith("https://"):
                        discovered_urls.append(href)
                        
                # Match urls
                for url in discovered_urls:
                    low_url = url.lower()
                    if "linkedin.com/in/" in low_url and not social_profiles["linkedin"]:
                        if validate_url(url): social_profiles["linkedin"] = url
                    elif "facebook.com/" in low_url and not social_profiles["facebook"]:
                        if validate_url(url): social_profiles["facebook"] = url
                    elif "instagram.com/" in low_url and not social_profiles["instagram"]:
                        if validate_url(url): social_profiles["instagram"] = url
                    elif "youtube.com/" in low_url and not social_profiles["youtube"]:
                        if validate_url(url): social_profiles["youtube"] = url
                    elif "google.com/maps" in low_url and not social_profiles["google_business_profile"]:
                        if validate_url(url): social_profiles["google_business_profile"] = url
            except Exception as se_err:
                logger.error(f"Error during social profile discovery: {se_err}")

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"AMFI search finished in {duration}s. Fields scraped: {list(mapped_data.keys())}")
        
        response_q.put({
            "status": "SUCCESS",
            "data": mapped_data,
            "social_profiles": social_profiles
        })

    except Exception as e:
        logger.error(f"Error in amfi_worker: {e}", exc_info=True)
        response_q.put({
            "status": "ERROR",
            "message": str(e) or "An error occurred during execution."
        })
    finally:
        # Clean up browser resources locally on this thread!
        try:
            if page: page.close()
            if context: context.close()
            if browser: browser.close()
            if playwright_inst: playwright_inst.stop()
        except Exception as clean_err:
            logger.error(f"Error cleaning up AMFI worker resources: {clean_err}")

class AMFIScraperService:
    @staticmethod
    def perform_lookup(arn_number):
        """Launches background worker thread to search AMFI."""
        response_q = queue.Queue()
        t = threading.Thread(
            target=amfi_worker,
            args=(arn_number, response_q),
            daemon=True
        )
        t.start()
        
        try:
            result = response_q.get(timeout=35) # Wait up to 35 seconds
            return result
        except queue.Empty:
            logger.error(f"Timeout waiting for results from AMFI worker thread for ARN {arn_number}")
            return {
                "status": "ERROR",
                "message": "AMFI website did not respond. Please try again."
            }

    @staticmethod
    def map_fields(raw_data):
        """Maps AMFI portal table labels to local fields."""
        mapped = {}
        
        mapping_keys = {
            "arn_number": ["arn number", "arn code", "arn"],
            "distributor_name": ["distributor name", "arn holder's name", "name", "holder name"],
            "arn_status": ["arn status", "status"],
            "license_valid_till": ["arn valid till", "valid till", "expiry date", "valid till date"],
            "euin_number": ["euin", "euin number"],
            "distributor_category": ["category", "distributor category"],
            "address": ["address", "current address"],
            "city": ["city"],
            "district": ["district"],
            "state": ["state"],
            "pincode": ["pincode", "pin code", "pin"]
        }
        
        # Case insensitive mapping
        for local_field, amfi_fields in mapping_keys.items():
            for key, val in raw_data.items():
                if any(f in key.lower() for f in amfi_fields):
                    cleaned_val = val.strip()
                    if local_field == "license_valid_till":
                        # Standardize format for date inputs (YYYY-MM-DD)
                        cleaned_val = cleaned_val.strip()
                        date_parsed = False
                        
                        # Try custom locale-independent MMM parser (e.g. "06 Oct 2028")
                        normalized_date = re.sub(r'[-/]', ' ', cleaned_val)
                        parts = normalized_date.split()
                        if len(parts) == 3:
                            day_str, mon_str, yr_str = parts[0], parts[1].lower()[:3], parts[2]
                            months_map = {
                                "jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                                "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"
                            }
                            if mon_str in months_map and day_str.isdigit() and yr_str.isdigit():
                                cleaned_val = f"{yr_str}-{months_map[mon_str]}-{int(day_str):02d}"
                                date_parsed = True
                                
                        if not date_parsed:
                            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d-%b-%Y"):
                                try:
                                    dt = datetime.strptime(cleaned_val, fmt)
                                    cleaned_val = dt.strftime("%Y-%m-%d")
                                    break
                                except ValueError:
                                    continue
                    mapped[local_field] = cleaned_val
                    break
                    
        # Parse multiple service pincodes or cities if they exist in the raw address or city field
        if "pincode" in mapped:
            mapped["service_pincodes"] = [mapped["pincode"]]
        if "city" in mapped:
            mapped["service_cities"] = [mapped["city"]]
            
        # Default status to Active if found
        if "arn_status" not in mapped or not mapped["arn_status"]:
            mapped["arn_status"] = "Active"
            
        # Ensure normalized ARN format in output
        if "arn_number" in mapped and mapped["arn_number"] and not mapped["arn_number"].upper().startswith("ARN-"):
            mapped["arn_number"] = f"ARN-{mapped['arn_number']}"
            
        return mapped
