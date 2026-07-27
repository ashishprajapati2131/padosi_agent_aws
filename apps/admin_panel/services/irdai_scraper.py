import os
import uuid
import base64
import logging
import threading
import queue
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Registry to keep track of active browser sessions (input_queue, response_queue, thread, timestamp)
SESSION_REGISTRY = {}
SESSION_TTL_MINUTES = 5

def cleanup_stale_sessions():
    """Removes sessions older than SESSION_TTL_MINUTES."""
    now = datetime.now()
    stale_keys = []
    for key, session in SESSION_REGISTRY.items():
        if now - session.get("timestamp", now) > timedelta(minutes=SESSION_TTL_MINUTES):
            stale_keys.append(key)

    for key in stale_keys:
        logger.info(f"Cleaning up stale IRDAI lookup session: {key}")
        session = SESSION_REGISTRY.pop(key, None)
        if session:
            try:
                session["input_queue"].put({"action": "STOP"})
            except Exception as e:
                logger.error(f"Error signaling stop to stale session thread: {e}")

def irdai_worker(pan_number, input_q, response_q):
    from playwright.sync_api import sync_playwright
    playwright_inst = None
    browser = None
    context = None
    page = None
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
        page.set_default_timeout(15000)

        # 1. Load page and fill PAN
        page.goto("https://agencyportal.irdai.gov.in/PublicAccess/LookUpPAN.aspx")
        page.check("#ctl00_ContentPlaceHolder1_RadioButtonPanAdhar_0")
        page.wait_for_timeout(500)
        page.fill("#ctl00_ContentPlaceHolder1_PAN_Details", pan_number)

        # 2. Capture CAPTCHA
        captcha_elem = page.locator("#ctl00_ContentPlaceHolder1_imgcaptcha")
        if not captcha_elem.is_visible():
            page.wait_for_selector("#ctl00_ContentPlaceHolder1_imgcaptcha", timeout=5000)
        captcha_bytes = captcha_elem.screenshot()
        captcha_base64 = base64.b64encode(captcha_bytes).decode('utf-8')

        # Push to response queue
        response_q.put({
            "status": "CAPTCHA_REQUIRED",
            "captcha_image": f"data:image/png;base64,{captcha_base64}"
        })

        # 3. Wait for captcha solution
        try:
            msg = input_q.get(timeout=SESSION_TTL_MINUTES * 60)
        except queue.Empty:
            logger.info(f"Worker thread for PAN {pan_number} timed out waiting for input.")
            return

        if msg.get("action") == "STOP":
            logger.info("Worker thread received STOP signal.")
            return

        captcha_solution = msg.get("captcha_solution")

        # 4. Fill CAPTCHA and submit
        page.fill("#ctl00_ContentPlaceHolder1_txtcaptcha", captcha_solution)
        page.click("#ctl00_ContentPlaceHolder1_btn_lookup")

        # Wait for network idle or load state
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # Check for error labels indicating invalid CAPTCHA or no record found.
        error_elem = page.locator("[id*='error'], [id*='Message'], [id*='lbl_err']").first
        if error_elem.is_visible():
            error_text = error_elem.text_content().strip()
            if error_text:
                response_q.put({
                    "status": "ERROR",
                    "message": error_text
                })
                return

        # Extract data from tables/grids on the page
        data = {}
        tables = page.query_selector_all("table")
        found_data = False
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
            headers = [th.text_content().strip() for th in table.query_selector_all("th")]
            if headers:
                rows = table.query_selector_all("tr")
                for r in rows:
                    tds = r.query_selector_all("td")
                    if len(tds) == len(headers):
                        for h, td in zip(headers, tds):
                            key = h
                            val = td.text_content().strip()
                            if key and val:
                                if "//<![CDATA[" in key or "//<![CDATA[" in val or len(key) > 100:
                                    continue
                                data[key] = val
                                found_data = True

        if not found_data or len(data) < 2:
            body_text = page.locator("body").text_content()
            if "no record" in body_text.lower() or "not found" in body_text.lower():
                response_q.put({
                    "status": "ERROR",
                    "message": "No record found for the provided PAN Number."
                })
            else:
                response_q.put({
                    "status": "ERROR",
                    "message": "Failed to extract data. The IRDAI portal structure may have changed, or CAPTCHA was invalid."
                })
            return

        response_q.put({
            "status": "SUCCESS",
            "data": data
        })

    except Exception as e:
        logger.error(f"Error in irdai_worker for PAN {pan_number}: {e}", exc_info=True)
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
        except Exception as e:
            logger.error(f"Error cleaning up worker resources: {e}")

class IRDAIScraperService:
    @staticmethod
    def initiate_lookup(pan_number):
        cleanup_stale_sessions()
        session_id = str(uuid.uuid4())
        
        input_q = queue.Queue()
        response_q = queue.Queue()
        
        # Start background worker thread
        t = threading.Thread(target=irdai_worker, args=(pan_number, input_q, response_q))
        t.daemon = True
        t.start()
        
        try:
            # Wait for CAPTCHA or error from the worker thread
            result = response_q.get(timeout=15) # Wait up to 15 seconds for initial load
            if result.get("status") == "CAPTCHA_REQUIRED":
                # Save session state in registry
                SESSION_REGISTRY[session_id] = {
                    "input_queue": input_q,
                    "response_queue": response_q,
                    "thread": t,
                    "timestamp": datetime.now(),
                    "pan": pan_number
                }
                return {
                    "status": "CAPTCHA_REQUIRED",
                    "session_id": session_id,
                    "captcha_image": result["captcha_image"]
                }
            return result
        except queue.Empty:
            logger.error(f"Timeout waiting for CAPTCHA from worker thread for PAN {pan_number}")
            return {
                "status": "ERROR",
                "message": "Timeout loading verification page. Please try again."
            }
        except Exception as e:
            logger.error(f"Error in initiate_lookup for PAN {pan_number}: {e}", exc_info=True)
            return {
                "status": "ERROR",
                "message": str(e) or "Failed to load verification page."
            }

    @staticmethod
    def resume_lookup(session_id, captcha_solution):
        cleanup_stale_sessions()
        session = SESSION_REGISTRY.pop(session_id, None)
        
        if not session:
            return {
                "status": "ERROR",
                "message": "Session expired or invalid. Please try again."
            }
            
        input_q = session["input_queue"]
        response_q = session["response_queue"]
        
        try:
            # Send CAPTCHA solution to worker thread
            input_q.put({
                "action": "SOLVE",
                "captcha_solution": captcha_solution
            })
            
            # Wait for result from worker thread
            result = response_q.get(timeout=25) # Wait up to 25 seconds for solver and scraping
            if result.get("status") == "SUCCESS":
                mapped_data = IRDAIScraperService.map_fields(result["data"])
                return {
                    "status": "SUCCESS",
                    "data": mapped_data,
                    "raw_data": result["data"]
                }
            return result
        except queue.Empty:
            logger.error(f"Timeout waiting for results from worker thread for session {session_id}")
            return {
                "status": "ERROR",
                "message": "Timeout waiting for IRDAI verification results."
            }
        except Exception as e:
            logger.error(f"Error in resume_lookup for session {session_id}: {e}", exc_info=True)
            return {
                "status": "ERROR",
                "message": str(e) or "Failed to process verification results."
            }

    @staticmethod
    def map_fields(raw_data):
        """Maps IRDAI portal table labels to local fields."""
        mapped = {}
        
        # Helper dictionary for mapping variations
        mapping_keys = {
            "license_number": ["license number", "licence no", "license no.", "license no", "licence number", "agency code", "agent code", "code"],
            "license_valid_till": ["valid till", "expiry date", "validity", "valid up to", "license valid till", "date of appointment", "status change date"],
            "agent_name": ["agent name", "name", "candidate name", "fullname"],
            "agency_name": ["agency name", "company name", "insurer name", "company", "insurer"],
            "agency_code": ["agency code", "code", "agent code"],
            "license_status": ["status of agency", "status change date", "status"],
            "designation": ["designation"],
            "category": ["category"],
            "address": ["address", "current address", "communication address"],
            "state": ["state"],
            "city": ["city", "district"],
            "pincode": ["pincode", "pin code", "pin"],
            "email": ["email", "e-mail", "email id"],
            "mobile": ["mobile", "phone", "contact", "mobile number"]
        }
        
        # Case insensitive mapping
        for local_field, irda_fields in mapping_keys.items():
            for key, val in raw_data.items():
                if any(f in key.lower() for f in irda_fields):
                    # Clean/normalize value
                    cleaned_val = val.strip()
                    # Try to parse valid dates if it's a date field
                    if local_field == "license_valid_till":
                        # Standardize format for date inputs (YYYY-MM-DD)
                        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
                            try:
                                dt = datetime.strptime(cleaned_val, fmt)
                                cleaned_val = dt.strftime("%Y-%m-%d")
                                break
                            except ValueError:
                                continue
                    mapped[local_field] = cleaned_val
                    break
                    
        return mapped
