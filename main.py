# -*- coding: utf-8 -*-
"""
Main entry point for LinkedIn automation.

Usage:
    python main.py connect    - Send connection requests
    python main.py message    - Send messages
"""

import sys
import logging

# Configure logging (show INFO and above in console).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 1. CONFIGURATION.
from config import USERNAME, PASSWORD

# 2. SUPPORTING FUNCTIONS.
from support import display_screenshot, display_full_screenshot

# 3. GOOGLE SHEETS CONNECTION.
from google_sheet import connect_google_sheet, update_google_sheet

# 4. DRIVER SETUP.
from driver import create_driver

# 5. LOGIN FUNCTIONS.
from login import login, LoginError, SecurityChallengeError

# 6. XPATH SETTINGS.
from xpath_config import STATUS_CONNECT

# 7. TASK FUNCTIONS.
from connect_linkedin import check_connection
from message_linkedin import check_datum, send_message

# =============================================
# SELENIUM IMPORTS (for main logic).
# =============================================
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def run_connect(driver, sheet, df):
    """Execute LinkedIn connection automation."""
    for index, row in df.iterrows():
        # Go to profile link.
        profile_link = row['Link']
        print(f"Visiting profile: {profile_link}", end=" ")
        driver.get(profile_link)
        display_full_screenshot(driver)
        status = ""

        # Wait for the page to load before checking connection.
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, STATUS_CONNECT)))
            # Check connection and send without note.
            status = check_connection(driver, row["EMAIL"])
        except Exception:
            status = "CONNECTED"

        df.at[index, 'STATUS'] = status

    # Update Google Sheet data.
    update_google_sheet(sheet, df)
    print("\nINFO: Connection task completed!")


def run_message(driver, sheet, df):
    """Execute LinkedIn messaging automation."""
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

    # Update Google Sheet data.
    update_google_sheet(sheet, df)
    print("\nINFO: Messaging task completed!")


def main():
    """Main function orchestrating the LinkedIn automation workflow."""
    # Parse command-line argument.
    if len(sys.argv) < 2 or sys.argv[1] not in ("connect", "message"):
        print("Usage: python main.py <connect|message>")
        print("  connect  - Send connection requests to profiles")
        print("  message  - Send messages to connected profiles")
        sys.exit(1)

    mode = sys.argv[1]
    driver = None

    try:
        # 1. SET UP DRIVER.
        print("=" * 50)
        print("SETTING UP DRIVER...")
        print("=" * 50)
        driver = create_driver()

        # 2. CONNECT TO GOOGLE SHEETS.
        print("=" * 50)
        print("CONNECTING TO GOOGLE SHEETS...")
        print("=" * 50)
        sheet, df = connect_google_sheet()

        # 3. DISPLAY GOOGLE SHEETS DATA.
        print("=" * 50)
        print("GOOGLE SHEETS DATA:")
        print("=" * 50)
        print(df.head())

        # 4. LOGIN TO LINKEDIN.
        print("=" * 50)
        print("LOGGING IN TO LINKEDIN...")
        print("=" * 50)
        try:
            login(driver, USERNAME, PASSWORD)
        except LoginError as e:
            print(f"\n❌  FATAL: Cannot log in to LinkedIn: {e}")
            print("   Please check your credentials in config.py and try again.")
            sys.exit(2)
        except SecurityChallengeError as e:
            print(f"\n❌  FATAL: Unresolvable security challenge: {e}")
            print("   LinkedIn may have flagged this account. Try logging in manually first.")
            sys.exit(3)

        # 5. EXECUTE TASK.
        print("=" * 50)
        print(f"EXECUTING TASK: {mode.upper()}...")
        print("=" * 50)

        if mode == "connect":
            run_connect(driver, sheet, df)
        elif mode == "message":
            run_message(driver, sheet, df)

        # 6. END PROGRAM.
        print("=" * 50)
        print("PROGRAM COMPLETED!")
        print("=" * 50)

    except KeyboardInterrupt:
        print("\n\n⚠️  Program interrupted by user.")
    except Exception as e:
        print(f"\n❌  Unexpected error: {e}")
        logging.exception("Unhandled exception in main():")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            print("INFO: Browser closed.")


if __name__ == "__main__":
    main()
