# -*- coding: utf-8 -*-
"""Login-related functions for LinkedIn automation.

NEW APPROACH — Profile-based login
===================================
Instead of filling in the username/password form (which is easily detected
by LinkedIn's bot-protection and triggers CAPTCHAs / security challenges),
this module relies on a **persistent Chrome profile**.

How it works:
  1. Run ``python main.py setup`` once.  This opens a *visible* Chrome
     window and navigates to LinkedIn.  You log in manually (solving any
     CAPTCHAs or 2FA yourself) and then press ENTER in the terminal.
     The session is saved into ``chrome_profile/``.
  2. On subsequent runs the same Chrome profile is reused.  LinkedIn
     already has your session cookies, so no login form interaction is
     needed.

Fall-back:
  If the saved session has expired (cookies cleared, LinkedIn forced a
  logout, etc.) the module will **attempt** one automatic credential
  login.  If that also fails it will open a visible browser for manual
  re-login.
"""

import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

from config import (
    MAX_LOGIN_RETRIES,
    RETRY_BACKOFF_BASE,
    SETUP_LOGIN_TIMEOUT,
    CHROME_PROFILE_DIR,
)
from support import display_screenshot, capture_full_page_screenshot

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LINKEDIN_BASE = "https://www.linkedin.com"
LINKEDIN_LOGIN = f"{LINKEDIN_BASE}/login"
LINKEDIN_FEED = f"{LINKEDIN_BASE}/feed"

# XPATHs / selectors used during login (kept for the auto-fill fallback)
XPATH_USERNAME = '//*[@id="username"]'
XPATH_PASSWORD = '//*[@id="password"]'
XPATH_LOGIN_BUTTON = (
    '//button[contains(@class, "btn__primary--large") and @aria-label="Sign in"]'
)

# Multiple selectors that indicate we are logged in
LOGIN_SUCCESS_INDICATORS = [
    (By.CSS_SELECTOR, ".global-nav__me-photo"),
    (By.CSS_SELECTOR, ".feed-identity-module"),
    (By.CSS_SELECTOR, "[data-control-name='identity_welcome_message']"),
    (By.CSS_SELECTOR, ".global-nav__primary-items"),
    (By.CSS_SELECTOR, "div.feed-sort-header"),
]


class LoginError(Exception):
    """Raised when LinkedIn login fails after all retries."""


class SecurityChallengeError(Exception):
    """Raised when an unresolvable security challenge is encountered."""


# ===================================================================
# LOGIN VERIFICATION HELPERS
# ===================================================================

def _is_logged_in(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    """Check whether the user is currently logged in.

    Tries multiple indicators because LinkedIn's DOM varies by account
    type (Premium vs Free) and A/B test variants.
    """
    for by, selector in LOGIN_SUCCESS_INDICATORS:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            logger.info("Login confirmed via selector: %s", selector)
            return True
        except TimeoutException:
            continue

    # Fallback: check URL — logged-in users are redirected away from /login.
    current = driver.current_url
    if "/feed" in current or "/mynetwork" in current or "/in/" in current:
        logger.info("Login confirmed via URL: %s", current)
        return True

    return False


def handle_cookie_acceptance(driver: webdriver.Chrome):
    """Accept cookies banner if present."""
    cookie_accept_selectors = [
        "//button[span[text()='Accept']]",
        "//button[contains(text(), 'Accept')]",
        "//button[contains(@class, 'artdeco-global-alert__action')]",
        "//button[@action-type='GLUE_UP_COOKIE_ACCEPT']",
    ]
    for xpath in cookie_accept_selectors:
        try:
            btn = driver.find_element(By.XPATH, xpath)
            btn.click()
            logger.info("Cookie consent banner accepted.")
            return
        except (NoSuchElementException, WebDriverException):
            continue
    logger.debug("No cookie consent banner detected (or already accepted).")


# ===================================================================
# CREDENTIAL AUTO-FILL  (fallback only)
# ===================================================================

def _try_credential_login(driver: webdriver.Chrome, username: str, password: str) -> bool:
    """Attempt a single username/password login.

    Returns True if login succeeded, False otherwise.
    This is used **only** as a fallback when the saved Chrome profile
    session has expired.
    """
    driver.get(LINKEDIN_LOGIN)
    time.sleep(3)

    handle_cookie_acceptance(driver)

    try:
        username_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XPATH_USERNAME))
        )
        password_field = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, XPATH_PASSWORD))
        )
        login_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_LOGIN_BUTTON))
        )
    except TimeoutException:
        logger.warning("Login form elements not found (page layout may have changed).")
        return False

    username_field.clear()
    username_field.send_keys(username)
    time.sleep(0.5)

    password_field.clear()
    password_field.send_keys(password)
    time.sleep(0.5)

    login_button.click()
    time.sleep(5)

    # Quick check
    if _is_logged_in(driver, timeout=10):
        return True

    return False


# ===================================================================
# SETUP  (one-time manual login)
# ===================================================================

def setup_login():
    """Open a visible browser so the user can log in manually.

    Call via ``python main.py setup``.  The Chrome profile directory is
    shared with the automated runs, so after a successful manual login
    the cookies persist for headless runs.
    """
    from driver import create_driver  # local import to avoid circular deps

    print("=" * 60)
    print("  LINKEDIN MANUAL LOGIN SETUP")
    print("=" * 60)
    print()
    print("A Chrome window will open.  Please:")
    print("  1. Log in to LinkedIn as you normally would.")
    print("  2. Solve any CAPTCHA or 2FA challenges.")
    print("  3. Wait until you see the LinkedIn home feed.")
    print("  4. Come back here and press ENTER.")
    print()

    driver = create_driver(headless=False)

    try:
        driver.get(LINKEDIN_LOGIN)
        handle_cookie_acceptance(driver)

        input("👉  Press ENTER after you have logged in successfully... ")

        # Validate
        driver.get(LINKEDIN_FEED)
        time.sleep(3)

        if _is_logged_in(driver, timeout=15):
            print("\n✅  Login verified! Session saved to the Chrome profile.")
            print("    You can now run 'python main.py connect' or 'python main.py message'.")
        else:
            print("\n⚠️  Could not verify login.  Make sure you are on the LinkedIn feed")
            print("    and try running 'python main.py setup' again.")
    finally:
        driver.quit()


# ===================================================================
# MAIN LOGIN FLOW  (used by connect / message tasks)
# ===================================================================

def login(driver: webdriver.Chrome, username: str, password: str):
    """Log in to LinkedIn using the persistent Chrome profile.

    Flow:
      1. Navigate to the feed — if the profile still has a valid session,
         LinkedIn will load the feed directly (no login needed).
      2. If the session expired, try one automatic credential login.
      3. If that also fails, prompt the user to run ``python main.py setup``.

    Raises:
        LoginError: If login fails and manual setup is needed.
    """
    # ── 1. Check existing session via profile cookies ─────────────
    print("INFO: Checking existing LinkedIn session...")
    driver.get(LINKEDIN_FEED)
    time.sleep(4)

    handle_cookie_acceptance(driver)

    if _is_logged_in(driver, timeout=10):
        print("✅  Already logged in via saved Chrome profile!")
        return

    print("INFO: Session expired or not found.  Attempting credential login...")

    # ── 2. Try credential login (up to MAX_LOGIN_RETRIES) ────────
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        print(f"INFO: Login attempt {attempt}/{MAX_LOGIN_RETRIES}...")

        success = _try_credential_login(driver, username, password)
        if success:
            print("✅  Login successful!")
            try:
                display_screenshot(driver)
            except Exception:
                pass
            return

        # Not logged in — check if we hit a challenge page
        current_url = driver.current_url
        if "/checkpoint" in current_url or "/challenge" in current_url:
            print(f"🔒  Security challenge detected at: {current_url}")
            capture_full_page_screenshot(driver, "login_challenge.png")
            print("    ⚠️  Please run  'python main.py setup'  to log in manually.")

        if attempt < MAX_LOGIN_RETRIES:
            wait = RETRY_BACKOFF_BASE * attempt
            print(f"⏳  Waiting {wait}s before retrying...")
            time.sleep(wait)

    # ── 3. All retries exhausted ──────────────────────────────────
    capture_full_page_screenshot(driver, "login_failed_final.png")
    error_msg = (
        f"Login failed after {MAX_LOGIN_RETRIES} attempts.  "
        f"Please run  'python main.py setup'  to log in manually first.  "
        f"Screenshot saved as 'login_failed_final.png'."
    )
    print(f"❌  {error_msg}")
    raise LoginError(error_msg)
