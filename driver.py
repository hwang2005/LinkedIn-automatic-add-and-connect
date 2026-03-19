# -*- coding: utf-8 -*-
"""Chrome WebDriver setup for LinkedIn automation.

Uses a persistent Chrome profile directory so that login sessions,
cookies, and local-storage survive across runs.  This makes LinkedIn
treat the browser as a genuine returning user instead of a fresh bot.
"""

import os
from selenium import webdriver

from config import WINDOW_SIZE, CHROME_PROFILE_DIR


def create_driver(headless: bool = True):
    """Create and return a configured Chrome WebDriver instance.

    Args:
        headless: If True (default), run in headless mode.
                  Pass False during the initial setup so the user
                  can log in manually (see `python main.py setup`).
    """
    # Ensure the profile directory exists.
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)

    options = webdriver.ChromeOptions()

    # ── Persistent profile ────────────────────────────────────────
    # user-data-dir keeps cookies, localStorage, and session data
    # across runs so LinkedIn does not ask you to log in every time.
    options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")

    # ── Anti-detection tweaks ─────────────────────────────────────
    # Exclude the "enable-automation" flag so window.navigator.webdriver
    # does not give us away.
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # ── Standard flags ────────────────────────────────────────────
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={WINDOW_SIZE}")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # A real-looking user-agent string.
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)

    # Override the webdriver flag via CDP so LinkedIn's JS checks
    # do not see us as automated.
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """
        },
    )

    return driver
