# -*- coding: utf-8 -*-
"""LinkedIn messaging automation - send messages to connections."""

import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

from config import USERNAME, PASSWORD, ATTACHMENT_BASE_URL
from xpath_config import (
    BUTTON_MESSAGE, FIELD_MESSAGE, FIELD_ATTACHMENT,
    BUTTON_SUBMIT_MESSAGE,
)
from driver import create_driver
from google_sheet import connect_google_sheet, update_google_sheet
from login import login
from support import display_screenshot, download_file


def check_datum(datum):
    """Validate the data for a single profile before sending a message."""
    # Check name.
    name = datum["Name"]
    if not name:
        print("ERROR: NAME NOT FOUND!")
        return "ERROR: NAME NOT FOUND!"

    # Check message.
    message = datum["Message"]
    if not message:
        print("ERROR: MESSAGE NOT FOUND!")
        return "ERROR: MESSAGE NOT FOUND!"

    # Check attachment.
    attachment = datum["Attachment"]
    if attachment:
        abs_path = os.path.abspath(attachment)
        # Download the attachment if it doesn't exist locally.
        if not os.path.exists(abs_path):
            try:
                download_file(ATTACHMENT_BASE_URL + attachment, abs_path)
            except Exception as e:
                print(f"ERROR: ATTACHMENT DOWNLOAD FAILED! {e}")
                return "ERROR: ATTACHMENT NOT FOUND"
    else:
        abs_path = ""

    # Process message template.
    message = message.replace("{{Name}}", name)

    return name, message, abs_path


def send_message(driver: webdriver.Chrome, target_profile: str, datum: tuple):
    """Send a message to a LinkedIn profile."""
    name, message, attachment = datum

    try:
        # Find the message dialog open button.
        c = EC.presence_of_element_located((By.XPATH, BUTTON_MESSAGE))
        try:
            e = WebDriverWait(driver, 15).until(c)
        except:
            print("ERROR: OPEN BUTTON NOT FOUND!")
            return "ERROR: OPEN BUTTON NOT FOUND!"

        # Check if the button is actually a message button.
        status = e.get_attribute("aria-label")
        if "Message" not in status:
            print("ERROR: BUTTON IS NOT MESSAGE BUTTON!")
            return "ERROR: BUTTON IS NOT MESSAGE BUTTON!"

        # Click the button.
        e.click()
        time.sleep(2)

        # Find the message input field.
        try:
            e = driver.find_element(By.CLASS_NAME, FIELD_MESSAGE)
        except NoSuchElementException:
            print("ERROR: MESSAGE BOX NOT FOUND!")
            return "ERROR: MESSAGE BOX NOT FOUND!"

        # Clear any default message.
        if e.text != "":
            e.send_keys(Keys.CONTROL + "a")
            e.send_keys(Keys.DELETE)
            time.sleep(2)

        # Type the message.
        e.send_keys(message)
        time.sleep(2)

        # Attach file if provided.
        if attachment:
            try:
                e = driver.find_element(By.CLASS_NAME, FIELD_ATTACHMENT)
            except NoSuchElementException:
                print("ERROR: ATTACHMENT BOX NOT FOUND!")
                return "ERROR: ATTACHMENT BOX NOT FOUND!"
            e.send_keys(attachment)
            display_screenshot(driver)
            time.sleep(2)

        # Find and click the send button.
        c = EC.presence_of_element_located((By.CLASS_NAME, BUTTON_SUBMIT_MESSAGE))
        try:
            e = WebDriverWait(driver, 15).until(c)
            driver.execute_script("arguments[0].click();", e)
        except:
            print("ERROR: SUBMIT BUTTON NOT FOUND!")
            return "ERROR: SUBMIT BUTTON NOT FOUND!"

        time.sleep(2)
        return "MESSAGE HAS SENT!"

    except Exception as e:
        print("\n" + str(e))
        return "ERROR: MESSAGE NOT SENT!"


def main():
    """Main entry point for LinkedIn messaging automation."""
    # Set up driver.
    driver = create_driver()

    # Login.
    login(driver, USERNAME, PASSWORD)

    # Connect to Google Sheets.
    sheet, df = connect_google_sheet()

    # Iterate through profiles and send messages.
    for index, row in df.iterrows():
        profile_link = row['Link']
        print(profile_link, end=" ")

        # Validate data.
        datum = check_datum(row)
        if isinstance(datum, str):
            status = datum
        else:
            driver.get(profile_link)
            # Send message.
            status = send_message(driver, profile_link, datum)
            display_screenshot(driver)

        # Save status.
        df.at[index, 'Status'] = status

    # Update Google Sheet with results.
    update_google_sheet(sheet, df)


if __name__ == "__main__":
    main()
