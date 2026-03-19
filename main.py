# -*- coding: utf-8 -*-
"""
Main entry point for LinkedIn automation.

Usage:
    python main.py setup      - One-time manual login (opens a visible browser)
    python main.py connect    - Send connection requests
    python main.py message    - Send messages
"""

import sys
import logging
import re
import unicodedata

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
from login import login, setup_login, LoginError, SecurityChallengeError

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


def _normalize_column_name(name: str) -> str:
    """Normalize a column name for case-insensitive and punctuation-insensitive matching."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.strip().lower())


def _resolve_column(df, primary_name: str, aliases=(), required=True):
    """
    Resolve a DataFrame column by primary name or aliases.

    Matching is case-insensitive and ignores spaces/underscores/punctuation.
    Returns the actual column name from df.columns, or None if optional and not found.
    """
    normalized_to_actual = {
        _normalize_column_name(col): col for col in df.columns
    }

    for candidate in (primary_name, *aliases):
        match = normalized_to_actual.get(_normalize_column_name(candidate))
        if match is not None:
            return match

    if required:
        available_columns = ", ".join([f"'{col}'" for col in df.columns])
        raise KeyError(
            f"Missing required column '{primary_name}'. "
            f"Please add/rename it in Google Sheets. Available columns: {available_columns}"
        )

    return None


def _prepare_message_columns(df):
    """Ensure message-mode columns exist with expected names used by check_datum()."""
    message_columns = {
        "Name": ("Full Name", "First Name", "Contact Name"),
        "Message": ("Msg", "Template", "Text"),
    }

    for canonical_name, aliases in message_columns.items():
        source_col = _resolve_column(df, canonical_name, aliases=aliases, required=True)
        if source_col != canonical_name:
            df.rename(columns={source_col: canonical_name}, inplace=True)

    attachment_col = _resolve_column(
        df, "Attachment", aliases=("File", "Attachment File"), required=False
    )
    if attachment_col is None:
        df["Attachment"] = ""
    elif attachment_col != "Attachment":
        df.rename(columns={attachment_col: "Attachment"}, inplace=True)


def _map_connect_status(raw_status: str) -> str:
    """
    Map raw connect result to the only two allowed sheet values:
    - 'Đã gửi connect'
    - 'Không tồn tại'
    """
    status_text = str(raw_status or "").upper()
    positive_markers = (
        "SUCCESS: CONNECT WITHOUT NOTE!",
        "PENDING",
        "CONNECTED",
    )
    if any(marker in status_text for marker in positive_markers):
        return "Đã gửi connect"
    return "Không tồn tại"


def run_connect(driver, sheet, df):
    """Execute LinkedIn connection automation."""
    link_col = _resolve_column(
        df,
        "Link",
        aliases=("Profile Link", "Profile URL", "URL", "LinkedIn URL", "LinkedIn"),
        required=True,
    )
    email_col = _resolve_column(df, "EMAIL", aliases=("Email", "E-mail"), required=False)
    status_col = _resolve_column(
        df,
        "Trạng thái kết nối",
        aliases=(
            "Trang thai ket noi",
            "Connection Status",
            "STATUS",
            "Status",
            "Result",
        ),
        required=False,
    )
    if status_col is None:
        status_col = "Trạng thái kết nối"
        df[status_col] = ""

    for index, row in df.iterrows():
        # Go to profile link.
        profile_link = str(row.get(link_col, "")).strip()
        if not profile_link:
            df.at[index, status_col] = "Không tồn tại"
            continue

        print(f"Visiting profile: {profile_link}", end=" ")
        driver.get(profile_link)
        display_full_screenshot(driver)
        status = ""

        # Wait for the page to load before checking connection.
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, STATUS_CONNECT)))
            # Check connection and send without note.
            status = check_connection(driver, row.get(email_col, "") if email_col else "")
        except Exception:
            status = "CONNECTED"

        df.at[index, status_col] = _map_connect_status(status)

    # Update Google Sheet data.
    update_google_sheet(sheet, df)
    print("\nINFO: Connection task completed!")


def run_message(driver, sheet, df):
    """Execute LinkedIn messaging automation."""
    _prepare_message_columns(df)
    link_col = _resolve_column(
        df,
        "Link",
        aliases=("Profile Link", "Profile URL", "URL", "LinkedIn URL", "LinkedIn"),
        required=True,
    )
    status_col = _resolve_column(
        df,
        "Status",
        aliases=("STATUS", "Result", "Message Status"),
        required=False,
    )
    if status_col is None:
        status_col = "Status"
        df[status_col] = ""

    for index, row in df.iterrows():
        profile_link = str(row.get(link_col, "")).strip()
        if not profile_link:
            df.at[index, status_col] = "ERROR: LINK NOT FOUND!"
            continue

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
        df.at[index, status_col] = status

    # Update Google Sheet data.
    update_google_sheet(sheet, df)
    print("\nINFO: Messaging task completed!")


def main():
    """Main function orchestrating the LinkedIn automation workflow."""
    # Parse command-line argument.
    valid_modes = ("setup", "connect", "message")
    if len(sys.argv) < 2 or sys.argv[1] not in valid_modes:
        print("Usage: python main.py <setup|connect|message>")
        print()
        print("  setup    - One-time manual login (opens a visible Chrome window)")
        print("  connect  - Send connection requests to profiles")
        print("  message  - Send messages to connected profiles")
        print()
        print("Run 'setup' first so LinkedIn saves your session.  After that,")
        print("'connect' and 'message' will reuse the saved session automatically.")
        sys.exit(1)

    mode = sys.argv[1]

    # ── SETUP MODE ─────────────────────────────────────────────
    if mode == "setup":
        setup_login()
        return

    # ── CONNECT / MESSAGE MODE ─────────────────────────────────
    driver = None

    try:
        # 1. SET UP DRIVER.
        print("=" * 50)
        print("SETTING UP DRIVER...")
        print("=" * 50)
        driver = create_driver(headless=True)

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
            print("   Please run  'python main.py setup'  to log in manually first.")
            sys.exit(2)
        except SecurityChallengeError as e:
            print(f"\n❌  FATAL: Unresolvable security challenge: {e}")
            print("   Please run  'python main.py setup'  to log in manually first.")
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
