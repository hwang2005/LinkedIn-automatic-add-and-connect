# -*- coding: utf-8 -*-
"""Login-related functions for LinkedIn automation."""

import os
import time
import pickle
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import COOKIES_FILE, CREDENTIALS_FILE
from support import display_screenshot, capture_full_page_screenshot


def login_with_cookies(driver: webdriver.Chrome):
    """Attempt to log in using saved cookies."""
    driver.get("https://www.linkedin.com")

    if os.path.exists(COOKIES_FILE):
        with open(COOKIES_FILE, "rb") as cookies_file:
            cookies = pickle.load(cookies_file)

        for cookie in cookies:
            driver.add_cookie(cookie)

        # Refresh the page to apply cookies.
        driver.refresh()
        time.sleep(3)
        return True
    return False


def save_cookies(driver: webdriver.Chrome):
    """Save current browser cookies to file."""
    with open(COOKIES_FILE, "wb") as cookies_file:
        pickle.dump(driver.get_cookies(), cookies_file)
    print("INFO: COOKIES SAVED!")


def load_cookies(driver: webdriver.Chrome, file_name: str):
    """Load cookies from a pickle file and add them to the browser."""
    if os.path.exists(file_name):
        with open(file_name, 'rb') as f:
            cookies = pickle.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)


def load_credentials():
    """Load saved login credentials from file."""
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "rb") as f:
            return pickle.load(f)
    return None


def save_credentials(username: str, password: str):
    """Save login credentials to file."""
    with open(CREDENTIALS_FILE, "wb") as f:
        pickle.dump({"username": username, "password": password}, f)


def handle_cookie_acceptance(driver: webdriver.Chrome):
    """Accept cookies banner if present."""
    try:
        driver.find_element(By.XPATH, "//button[span[text()='Accept']]").click()
        print("INFO: COOKIES IS ACCEPTED!")
    except:
        print("INFO: COOKIES IS NOT REQUIRED!")


def handle_code_verification(driver: webdriver.Chrome):
    """Handle email verification code input if required."""
    try:
        # Find verification field.
        ID_FIELD = "input__email_verification_pin"
        CONDITION = EC.presence_of_element_located((By.ID, ID_FIELD))
        verification_field = WebDriverWait(driver, 20).until(CONDITION)

        # Find submit button.
        ID_FIELD = "email-pin-submit-button"
        CONDITION = EC.presence_of_element_located((By.ID, ID_FIELD))
        submit_button = WebDriverWait(driver, 20).until(CONDITION)

        # Enter the verification code.
        code = input("Verification code required! Check your email and enter the code: ")
        verification_field.send_keys(code)
        time.sleep(1)
        submit_button.click()
        time.sleep(2)
    except:
        print("INFO: NO VERIFICATION DETECTED!")


def login(driver: webdriver.Chrome, username: str, password: str):
    """Log in to LinkedIn with username and password, using cookies if available."""
    XPATH_USERNAME = '//*[@id="username"]'
    XPATH_PASSWORD = '//*[@id="password"]'
    XPATH_LOGIN_BUTTON = '//button[contains(@class, "btn__primary--large") and @aria-label="Sign in"]'

    driver.get("https://www.linkedin.com/login")
    time.sleep(2)

    # Check if cookies exist and credentials have not changed.
    credentials = load_credentials()

    if os.path.exists(COOKIES_FILE) and credentials:
        if credentials['username'] == username and credentials['password'] == password:
            # Load cookies and try to log in.
            load_cookies(driver, COOKIES_FILE)
            driver.get("https://www.linkedin.com/feed")
            time.sleep(3)

            # Check if logged in by looking for user icon.
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'global-nav__me-photo')))
                print("INFO: Logged in using cookies!")
                return
            except:
                print("INFO: Cookies invalid, trying manual login...")

    # Manual login if credentials changed or no cookies.
    driver.get("https://www.linkedin.com/login")
    capture_full_page_screenshot(driver)

    username_field = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, XPATH_USERNAME)))
    password_field = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, XPATH_PASSWORD)))
    login_button = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, XPATH_LOGIN_BUTTON)))

    username_field.send_keys(username)
    time.sleep(2)
    password_field.send_keys(password)
    time.sleep(2)
    login_button.click()

    time.sleep(5)

    # Handle verification and cookie acceptance.
    handle_code_verification(driver)
    handle_cookie_acceptance(driver)

    # Save cookies and credentials after successful login.
    save_cookies(driver)
    save_credentials(username, password)
    print("INFO: Login successful! Cookies and credentials saved!")
    display_screenshot(driver)
