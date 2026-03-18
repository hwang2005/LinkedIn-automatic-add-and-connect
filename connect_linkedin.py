# -*- coding: utf-8 -*-
"""LinkedIn connection automation - send connection requests."""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from config import USERNAME, PASSWORD
from xpath_config import (
    STATUS_CONNECT, STATUS_MESSAGE, BUTTON_MORE,
    MORE_UNCONNECT, MORE_CONNECT, BUTTON_SEND_WITHOUT_NOTE,
)
from driver import create_driver
from google_sheet import connect_google_sheet, update_google_sheet
from login import login
from support import display_full_screenshot


def check_status(driver: webdriver.Chrome, xpath: str, *kws):
    """Check if an element's aria-label contains any of the given keywords."""
    try:
        status = driver.find_element(By.XPATH, xpath)
        status_text = status.get_attribute("aria-label")
        if status_text:
            for keyword in kws:
                if keyword in status_text:
                    return True
    except NoSuchElementException:
        print(f"Element not found: {xpath}")
    except Exception as e:
        print(f"An error occurred: {e}")
    return False


def check_status_in_more(driver: webdriver.Chrome):
    """Check the connection status from the MORE dropdown menu."""
    # Check unconnected status in MORE.
    if check_status(driver, MORE_UNCONNECT, "Invite"):
        return "UNCONNECTED"
    # Check connected status in MORE.
    if check_status(driver, MORE_CONNECT, "Remove your connection"):
        return "CONNECTED"
    return "UNKNOWN"


def find_element_in_list(driver: webdriver.Chrome, e_list: list):
    """Try to find the first available element from a list of XPATHs."""
    for e in e_list:
        try:
            return WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, e)))
        except TimeoutException:
            print(f"Timeout for element: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")
    return None


def send_connection(driver: webdriver.Chrome, xpath: str):
    """Send a connection request without a note."""
    try:
        # Click CONNECT button.
        try:
            e = WebDriverWait(driver, 10).until(EC.presence_of_element_located(
                (By.XPATH, '/html/body/div[6]/div[3]/div/div/div[2]/div/div/main/section[1]/div[2]/div[3]/div/button[1]')))
            e.click()
        except TimeoutException:
            return "ERROR: BUTTON CONNECT NOT FOUND"
        except Exception as ex:
            return f"ERROR: FAILED TO CLICK CONNECT BUTTON: {ex}"

        # Wait for the send-without-note button to appear.
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, BUTTON_SEND_WITHOUT_NOTE)))

        # Click SEND WITHOUT NOTE.
        try:
            e = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, BUTTON_SEND_WITHOUT_NOTE)))
            e.click()
        except TimeoutException:
            return "ERROR: BUTTON SEND WITHOUT NOTE NOT FOUND"
        except Exception as ex:
            return f"ERROR: FAILED TO CLICK SEND WITHOUT NOTE: {ex}"

        return "SUCCESS: CONNECT WITHOUT NOTE!"

    except Exception as e:
        print(f"\n {e}")
        return "ERROR: UNKNOWN"


def check_connection(driver: webdriver.Chrome, email: str, note: str = None):
    """Check the current connection status and send a connection request if unconnected."""
    try:
        # Check unconnected status.
        if check_status(driver, STATUS_CONNECT, "Invite"):
            status = send_connection(driver, STATUS_CONNECT)
            print(f"STATUS: {status}")
            return status

        # Check pending status.
        if check_status(driver, STATUS_CONNECT, "Pending"):
            print("STATUS: PENDING")
            return "PENDING"

        # Find and click MORE button.
        print("CHECKING IN MORE", end=" ")
        try:
            button_more = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, BUTTON_MORE)))
            button_more.click()
        except TimeoutException:
            print("ERROR: BUTTON MORE NOT FOUND!")
            return "ERROR: BUTTON MORE NOT FOUND!"
        except NoSuchElementException:
            print("ERROR: BUTTON MORE NOT FOUND!")
            return "ERROR: BUTTON MORE NOT FOUND!"

        # Check connected status via MESSAGE button.
        if check_status(driver, STATUS_MESSAGE, "Message", "Follow", "Following"):
            status = check_status_in_more(driver)
            if status == "UNCONNECTED":
                status = send_connection(driver, MORE_UNCONNECT)
            print(f"STATUS: {status}")
            return status

    except Exception as e:
        print(f"ERROR: {e}")
        return "ERROR: UNKNOWN"


def main():
    """Main entry point for LinkedIn connection automation."""
    # Set up driver.
    driver = create_driver()

    # Login.
    login(driver, USERNAME, PASSWORD)

    # Connect to Google Sheets.
    sheet, df = connect_google_sheet()

    # Iterate through profiles and send connection requests.
    for index, row in df.iterrows():
        profile_link = row['Link']
        print(f"Visiting profile: {profile_link}", end=" ")
        driver.get(profile_link)
        display_full_screenshot(driver)
        status = ""

        # Wait for the page to load before checking connection.
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, STATUS_CONNECT)))
            status = check_connection(driver, row["EMAIL"])
        except:
            status = "CONNECTED"

        df.at[index, 'STATUS'] = status

    # Update Google Sheet with results.
    update_google_sheet(sheet, df)


if __name__ == "__main__":
    main()
