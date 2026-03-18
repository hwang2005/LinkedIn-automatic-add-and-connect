# -*- coding: utf-8 -*-
"""Login-related functions for LinkedIn automation.

Handles cookie-based session restoration, manual credential login,
security challenge detection (CAPTCHA, verification codes, unusual activity),
and automatic retry with exponential backoff.
"""

import os
import time
import pickle
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

from config import COOKIES_FILE, CREDENTIALS_FILE, MAX_LOGIN_RETRIES, RETRY_BACKOFF_BASE
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

# MAX_LOGIN_RETRIES and RETRY_BACKOFF_BASE are imported from config.py

# XPATHs / selectors used during login
XPATH_USERNAME = '//*[@id="username"]'
XPATH_PASSWORD = '//*[@id="password"]'
XPATH_LOGIN_BUTTON = (
    '//button[contains(@class, "btn__primary--large") and @aria-label="Sign in"]'
)

# Multiple selectors that indicate a successful login
LOGIN_SUCCESS_INDICATORS = [
    (By.CSS_SELECTOR, ".global-nav__me-photo"),
    (By.CSS_SELECTOR, ".feed-identity-module"),
    (By.CSS_SELECTOR, "[data-control-name='identity_welcome_message']"),
    (By.CSS_SELECTOR, ".global-nav__primary-items"),
    (By.CSS_SELECTOR, "div.feed-sort-header"),
]

# Selectors that indicate security challenges
CHALLENGE_SELECTORS = {
    "captcha": [
        (By.ID, "captcha-internal"),
        (By.CSS_SELECTOR, "iframe[title*='captcha']"),
        (By.CSS_SELECTOR, "iframe[src*='captcha']"),
        (By.CSS_SELECTOR, ".recaptcha-checkbox"),
    ],
    "email_verification": [
        (By.ID, "input__email_verification_pin"),
    ],
    "phone_verification": [
        (By.ID, "input__phone_verification_pin"),
        (By.CSS_SELECTOR, "input[name='pin']"),
    ],
    "unusual_activity": [
        (By.CSS_SELECTOR, "h1.heading--header-1"),  # "Let's do a quick security check"
        (By.XPATH, "//*[contains(text(), 'unusual activity')]"),
        (By.XPATH, "//*[contains(text(), 'security verification')]"),
        (By.XPATH, "//*[contains(text(), 'security check')]"),
    ],
    "app_verification": [
        (By.XPATH, "//*[contains(text(), 'Approve from your')]"),
        (By.XPATH, "//*[contains(text(), 'two-step verification')]"),
    ],
}

# Selectors that indicate login failure
LOGIN_FAILURE_INDICATORS = [
    (By.ID, "error-for-username"),
    (By.ID, "error-for-password"),
    (By.CSS_SELECTOR, ".form__label--error"),
    (By.XPATH, "//*[contains(text(), \"credentials don't match\")]"),
    (By.XPATH, "//*[contains(text(), 'wrong password')]"),
    (By.XPATH, "//*[contains(text(), \"Hmm, we don't recognize\")]"),
    (By.XPATH, "//*[contains(text(), 'account has been restricted')]"),
]


class LoginError(Exception):
    """Raised when LinkedIn login fails after all retries."""
    pass


class SecurityChallengeError(Exception):
    """Raised when an unresolvable security challenge is encountered."""
    pass


# ===================================================================
# COOKIE MANAGEMENT
# ===================================================================

def save_cookies(driver: webdriver.Chrome):
    """Save current browser cookies to file."""
    try:
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        logger.info("Cookies saved to '%s'.", COOKIES_FILE)
    except Exception as exc:
        logger.warning("Failed to save cookies: %s", exc)


def load_cookies(driver: webdriver.Chrome, file_name: str):
    """Load cookies from a pickle file and add them to the browser."""
    if not os.path.exists(file_name):
        logger.info("Cookie file '%s' not found.", file_name)
        return False

    try:
        with open(file_name, "rb") as f:
            cookies = pickle.load(f)

        for cookie in cookies:
            # Skip cookies with domain mismatch or problematic attributes.
            try:
                driver.add_cookie(cookie)
            except WebDriverException:
                continue  # Some cookies may not apply to the current domain.

        logger.info("Loaded %d cookies from '%s'.", len(cookies), file_name)
        return True
    except (pickle.UnpicklingError, EOFError, FileNotFoundError) as exc:
        logger.warning("Corrupt cookie file '%s': %s — deleting.", file_name, exc)
        _safe_delete(file_name)
        return False


def _safe_delete(path: str):
    """Delete a file if it exists, suppressing errors."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ===================================================================
# CREDENTIAL MANAGEMENT
# ===================================================================

def load_credentials():
    """Load saved login credentials from file."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        with open(CREDENTIALS_FILE, "rb") as f:
            return pickle.load(f)
    except (pickle.UnpicklingError, EOFError):
        logger.warning("Corrupt credentials file — deleting.")
        _safe_delete(CREDENTIALS_FILE)
        return None


def save_credentials(username: str, password: str):
    """Save login credentials to file."""
    try:
        with open(CREDENTIALS_FILE, "wb") as f:
            pickle.dump({"username": username, "password": password}, f)
    except Exception as exc:
        logger.warning("Failed to save credentials: %s", exc)


# ===================================================================
# LOGIN VERIFICATION HELPERS
# ===================================================================

def _is_logged_in(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    """Check whether the user is currently logged in.

    Tries multiple indicators because LinkedIn's DOM varies by account type
    (Premium vs Free) and A/B test variants.
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


def _detect_login_failure(driver: webdriver.Chrome) -> str | None:
    """Return an error message if explicit login-failure indicators are present."""
    for by, selector in LOGIN_FAILURE_INDICATORS:
        try:
            el = driver.find_element(by, selector)
            text = el.text.strip() or el.get_attribute("textContent") or ""
            if text:
                return text
        except (NoSuchElementException, WebDriverException):
            continue
    return None


def _detect_challenge(driver: webdriver.Chrome) -> str | None:
    """Return the challenge type if a security challenge page is detected."""
    for challenge_type, selectors in CHALLENGE_SELECTORS.items():
        for by, selector in selectors:
            try:
                driver.find_element(by, selector)
                return challenge_type
            except (NoSuchElementException, WebDriverException):
                continue
    return None


# ===================================================================
# CHALLENGE HANDLERS
# ===================================================================

def _handle_challenge(driver: webdriver.Chrome, challenge_type: str):
    """Route to the appropriate challenge handler."""
    handlers = {
        "email_verification": _handle_email_verification,
        "phone_verification": _handle_phone_verification,
        "captcha": _handle_captcha,
        "unusual_activity": _handle_unusual_activity,
        "app_verification": _handle_app_verification,
    }
    handler = handlers.get(challenge_type, _handle_unknown_challenge)
    handler(driver)


def _handle_email_verification(driver: webdriver.Chrome):
    """Handle email verification code input."""
    logger.info("Email verification challenge detected.")
    try:
        pin_field = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "input__email_verification_pin"))
        )
        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "email-pin-submit-button"))
        )

        code = input(
            "\n🔐 EMAIL VERIFICATION REQUIRED!\n"
            "   Check your email and enter the verification code: "
        )
        pin_field.clear()
        pin_field.send_keys(code.strip())
        time.sleep(1)
        submit_btn.click()
        time.sleep(3)
        logger.info("Email verification code submitted.")
    except TimeoutException:
        raise SecurityChallengeError(
            "Email verification fields not found. LinkedIn may have changed its layout."
        )


def _handle_phone_verification(driver: webdriver.Chrome):
    """Handle phone/SMS verification code input."""
    logger.info("Phone verification challenge detected.")
    try:
        pin_field = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.ID, "input__phone_verification_pin"))
        )
        # Try multiple possible submit button selectors.
        submit_btn = None
        for selector in ["phone-pin-submit-button", "email-pin-submit-button"]:
            try:
                submit_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.ID, selector))
                )
                break
            except TimeoutException:
                continue

        if not submit_btn:
            # Fallback: find any submit button
            try:
                submit_btn = driver.find_element(
                    By.CSS_SELECTOR, "button[type='submit']"
                )
            except NoSuchElementException:
                raise SecurityChallengeError(
                    "Phone verification submit button not found."
                )

        code = input(
            "\n📱 PHONE VERIFICATION REQUIRED!\n"
            "   Check your phone and enter the verification code: "
        )
        pin_field.clear()
        pin_field.send_keys(code.strip())
        time.sleep(1)
        submit_btn.click()
        time.sleep(3)
        logger.info("Phone verification code submitted.")
    except (TimeoutException, NoSuchElementException):
        raise SecurityChallengeError(
            "Phone verification fields not found."
        )


def _handle_captcha(driver: webdriver.Chrome):
    """Handle CAPTCHA challenge — requires manual intervention."""
    logger.warning("CAPTCHA challenge detected!")
    capture_full_page_screenshot(driver, "captcha_screenshot.png")
    input(
        "\n🤖 CAPTCHA DETECTED!\n"
        "   Unfortunately, CAPTCHAs cannot be solved automatically.\n"
        "   Please solve the CAPTCHA manually in the browser,\n"
        "   then press ENTER to continue... "
    )
    time.sleep(2)


def _handle_unusual_activity(driver: webdriver.Chrome):
    """Handle 'unusual activity' / security check page."""
    logger.warning("Unusual activity security check detected!")
    capture_full_page_screenshot(driver, "security_check_screenshot.png")
    input(
        "\n⚠️  SECURITY CHECK DETECTED!\n"
        '   LinkedIn has flagged "unusual activity" on this login.\n'
        "   Please complete the security check manually in the browser,\n"
        "   then press ENTER to continue... "
    )
    time.sleep(2)


def _handle_app_verification(driver: webdriver.Chrome):
    """Handle two-factor / app-based verification."""
    logger.info("App-based two-step verification detected.")
    input(
        "\n📲 TWO-STEP VERIFICATION REQUIRED!\n"
        "   Please approve the login from your authenticator app,\n"
        "   then press ENTER to continue... "
    )
    time.sleep(5)


def _handle_unknown_challenge(driver: webdriver.Chrome):
    """Fallback handler for unrecognized challenges."""
    logger.warning("Unknown security challenge detected.")
    capture_full_page_screenshot(driver, "unknown_challenge_screenshot.png")
    input(
        "\n❓ UNKNOWN SECURITY CHALLENGE!\n"
        "   LinkedIn presented an unexpected security challenge.\n"
        "   A screenshot has been saved as 'unknown_challenge_screenshot.png'.\n"
        "   Please resolve it manually, then press ENTER to continue... "
    )
    time.sleep(2)


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
# MAIN LOGIN FLOW
# ===================================================================

def _login_with_cookies(driver: webdriver.Chrome, username: str, password: str) -> bool:
    """Try to restore a previous session via saved cookies.

    Returns True if the session was restored successfully.
    """
    credentials = load_credentials()
    if not credentials:
        return False

    # Only use cookies if the credentials haven't changed.
    if credentials.get("username") != username or credentials.get("password") != password:
        logger.info("Credentials changed — skipping cookie login.")
        _safe_delete(COOKIES_FILE)
        return False

    if not os.path.exists(COOKIES_FILE):
        return False

    # Navigate to LinkedIn first so cookies can be set on the correct domain.
    driver.get(LINKEDIN_BASE)
    time.sleep(2)

    if not load_cookies(driver, COOKIES_FILE):
        return False

    # Navigate to feed to test the session.
    driver.get(LINKEDIN_FEED)
    time.sleep(3)

    if _is_logged_in(driver, timeout=10):
        logger.info("Session restored from cookies!")
        return True

    logger.info("Saved cookies expired or invalid — falling back to manual login.")
    _safe_delete(COOKIES_FILE)
    return False


def _login_with_credentials(driver: webdriver.Chrome, username: str, password: str):
    """Perform a fresh login using username/password.

    Raises LoginError if the login form cannot be completed.
    """
    driver.get(LINKEDIN_LOGIN)
    time.sleep(2)

    # Accept cookie banner if present (on login page).
    handle_cookie_acceptance(driver)

    try:
        capture_full_page_screenshot(driver)
    except Exception:
        pass  # Screenshot is non-critical.

    # Fill in credentials.
    try:
        username_field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, XPATH_USERNAME))
        )
        password_field = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, XPATH_PASSWORD))
        )
        login_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, XPATH_LOGIN_BUTTON))
        )
    except TimeoutException:
        raise LoginError(
            "Login form elements not found. LinkedIn may have changed its page structure."
        )

    username_field.clear()
    username_field.send_keys(username)
    time.sleep(1)

    password_field.clear()
    password_field.send_keys(password)
    time.sleep(1)

    login_button.click()
    time.sleep(5)


def login(driver: webdriver.Chrome, username: str, password: str):
    """Log in to LinkedIn with retry logic, challenge handling, and session validation.

    This is the main entry point for the login flow:
    1. Try cookie-based session restoration.
    2. If that fails, perform credential-based login with up to MAX_LOGIN_RETRIES.
    3. After login, detect and handle any security challenges.
    4. Validate that the login actually succeeded.
    5. Save cookies/credentials for future runs.

    Raises:
        LoginError: If login fails after all retries.
        SecurityChallengeError: If an unresolvable challenge is hit.
    """
    # ── 1. Try cookie login ──────────────────────────────────────
    print("INFO: Attempting cookie-based login...")
    if _login_with_cookies(driver, username, password):
        print("✅  Logged in via saved cookies!")
        return

    # ── 2. Credential login with retries ─────────────────────────
    last_error = None
    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        print(f"INFO: Login attempt {attempt}/{MAX_LOGIN_RETRIES}...")

        try:
            _login_with_credentials(driver, username, password)
        except LoginError as exc:
            last_error = exc
            logger.warning("Login form error on attempt %d: %s", attempt, exc)
            wait = RETRY_BACKOFF_BASE * attempt
            print(f"⏳  Waiting {wait}s before retrying...")
            time.sleep(wait)
            continue

        # ── 3. Check for explicit login failure messages ─────────
        failure_msg = _detect_login_failure(driver)
        if failure_msg:
            print(f"❌  Login failed: {failure_msg}")
            logger.warning("Login failure on attempt %d: %s", attempt, failure_msg)
            last_error = LoginError(failure_msg)
            wait = RETRY_BACKOFF_BASE * attempt
            print(f"⏳  Waiting {wait}s before retrying...")
            time.sleep(wait)
            continue

        # ── 4. Check for security challenges ─────────────────────
        challenge = _detect_challenge(driver)
        if challenge:
            print(f"🔒  Security challenge detected: {challenge}")
            _handle_challenge(driver, challenge)
            time.sleep(3)

            # Re-check for additional challenges (e.g. CAPTCHA after verification).
            second_challenge = _detect_challenge(driver)
            if second_challenge:
                print(f"🔒  Additional challenge detected: {second_challenge}")
                _handle_challenge(driver, second_challenge)
                time.sleep(3)

        # ── 5. Accept cookie consent (post-login) ────────────────
        handle_cookie_acceptance(driver)

        # ── 6. Validate login success ────────────────────────────
        if _is_logged_in(driver, timeout=15):
            # Save session for next run.
            save_cookies(driver)
            save_credentials(username, password)
            print("✅  Login successful! Session saved.")
            try:
                display_screenshot(driver)
            except Exception:
                pass
            return
        else:
            # Not logged in — might be on a challenge page we didn't detect.
            current_url = driver.current_url
            logger.warning(
                "Login not confirmed after attempt %d. Current URL: %s",
                attempt, current_url,
            )
            print(f"⚠️  Login not confirmed. Current page: {current_url}")
            last_error = LoginError(
                f"Login not confirmed after attempt {attempt}. URL: {current_url}"
            )

            # If still on a challenge-like page, give user a chance to fix it.
            if "/checkpoint" in current_url or "/challenge" in current_url:
                capture_full_page_screenshot(driver, "login_challenge.png")
                input(
                    "\n⚠️  LinkedIn requires additional verification.\n"
                    "   A screenshot has been saved as 'login_challenge.png'.\n"
                    "   Please resolve it manually, then press ENTER to continue... "
                )
                if _is_logged_in(driver, timeout=10):
                    save_cookies(driver)
                    save_credentials(username, password)
                    print("✅  Login successful after manual challenge resolution!")
                    return

            wait = RETRY_BACKOFF_BASE * attempt
            print(f"⏳  Waiting {wait}s before retrying...")
            time.sleep(wait)

    # ── All retries exhausted ────────────────────────────────────
    capture_full_page_screenshot(driver, "login_failed_final.png")
    error_msg = (
        f"Login failed after {MAX_LOGIN_RETRIES} attempts. "
        f"Last error: {last_error}. "
        f"Screenshot saved as 'login_failed_final.png'."
    )
    print(f"❌  {error_msg}")
    raise LoginError(error_msg)
