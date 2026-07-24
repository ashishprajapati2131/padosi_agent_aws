import os
import logging
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

class PlaywrightManager:
    _instance = None
    _playwright = None
    _browser = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(PlaywrightManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def get_browser(self):
        if self._browser is None:
            try:
                self._playwright = sync_playwright().start()
                headless = os.getenv('PLAYWRIGHT_HEADLESS', 'True').lower() in ('true', '1', 'yes')
                self._browser = self._playwright.chromium.launch(
                    headless=headless,
                    args=["--disable-dev-shm-usage", "--no-sandbox"]
                )
                logger.info("Playwright browser launched successfully.")
            except Exception as e:
                logger.error(f"Failed to launch Playwright browser: {e}")
                self.shutdown()
                raise e
        return self._browser

    def new_page(self):
        browser = self.get_browser()
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        # Set default timeout to 15 seconds
        page.set_default_timeout(15000)
        return page, context

    def shutdown(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as e:
                logger.error(f"Error stopping Playwright: {e}")
            self._playwright = None

playwright_manager = PlaywrightManager()
