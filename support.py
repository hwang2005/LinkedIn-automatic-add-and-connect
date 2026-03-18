# -*- coding: utf-8 -*-
"""Supporting functions for LinkedIn automation."""

import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from IPython.display import Image, display
from PIL import Image as PILImage


def download_file(url: str, dest_path: str):
    """Download a file from a URL to the destination path (replaces Colab !wget).

    - Automatically converts GitHub blob URLs to raw content URLs.
    - Skips download if the file already exists locally.
    """
    if os.path.exists(dest_path):
        print(f"INFO: '{dest_path}' already exists, skipping download.")
        return dest_path

    # Convert GitHub blob URL to raw content URL.
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")

    print(f"INFO: Downloading '{url}' -> '{dest_path}'...")
    response = requests.get(url, stream=True)
    response.raise_for_status()

    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    print(f"INFO: Downloaded '{dest_path}' successfully.")
    return dest_path


def display_screenshot(driver: webdriver.Chrome, file_name: str = 'screenshot.png'):
    """Take a screenshot and display it."""
    driver.save_screenshot(file_name)
    time.sleep(5)
    display(Image(filename=file_name))


def display_full_screenshot(driver: webdriver.Chrome):
    """Take a full-page screenshot by resizing the window to match page height."""
    # Wait for the body element to be present.
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # Get the full page height.
    total_height = driver.execute_script("return document.body.scrollHeight")

    # Resize the browser window to match the full page height.
    driver.set_window_size(1920, total_height)

    # Take the screenshot.
    driver.save_screenshot('screenshot.png')

    # Display the screenshot.
    time.sleep(2)
    display(PILImage.open('screenshot.png'))


def capture_full_page_screenshot(driver: webdriver.Chrome, file_name: str = 'full_screenshot.png'):
    """Take a full-page screenshot using both scroll width and height."""
    total_width = driver.execute_script("return document.body.scrollWidth")
    total_height = driver.execute_script("return document.body.scrollHeight")
    driver.set_window_size(total_width, total_height)

    # Take the screenshot.
    driver.save_screenshot(file_name)

    # Display the screenshot.
    time.sleep(2)
    display(Image(filename=file_name))
