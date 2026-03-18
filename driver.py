# -*- coding: utf-8 -*-
"""Chrome WebDriver setup for LinkedIn automation."""

from selenium import webdriver

from config import WINDOW_SIZE


def create_driver():
    """Create and return a configured Chrome WebDriver instance."""
    options = webdriver.ChromeOptions()

    options.add_argument('--no-sandbox')
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument(f"--window-size={WINDOW_SIZE}")

    driver = webdriver.Chrome(options=options)
    return driver
