# -*- coding: utf-8 -*-
"""
Main entry point for LinkedIn automation.

Usage:
    python main.py setup
    python main.py connect [--linkedin-username USER --linkedin-password PASS]
    python main.py message [--linkedin-username USER --linkedin-password PASS]
    python main.py cron --task {connect,message} --schedule "0 9 * * *" \
        [--linkedin-username USER --linkedin-password PASS] [--install]
"""

import argparse
import logging
import ntpath
import os
import posixpath
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata

# Configure logging (show INFO and above in console).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 1. CONFIGURATION.
from config import BASE_DIR, PASSWORD as DEFAULT_PASSWORD, USERNAME as DEFAULT_USERNAME

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


logger = logging.getLogger(__name__)
TASK_MODES = ("setup", "connect", "message", "cron")
AUTOMATION_MODES = ("connect", "message")


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
    - 'ÄÃ£ gá»­i connect'
    - 'KhÃ´ng tá»“n táº¡i'
    """
    status_text = str(raw_status or "").upper()
    positive_markers = (
        "SUCCESS: CONNECT WITHOUT NOTE!",
        "PENDING",
        "CONNECTED",
    )
    if any(marker in status_text for marker in positive_markers):
        return "ÄÃ£ gá»­i connect"
    return "KhÃ´ng tá»“n táº¡i"


def _build_parser():
    """Create the CLI parser."""
    credential_parent = argparse.ArgumentParser(add_help=False)
    credential_parent.add_argument(
        "--linkedin-username",
        help="LinkedIn username/email. Overrides config.py and LINKEDIN_USERNAME.",
    )
    credential_parent.add_argument(
        "--linkedin-password",
        help="LinkedIn password. Overrides config.py and LINKEDIN_PASSWORD.",
    )

    parser = argparse.ArgumentParser(
        description="LinkedIn automation runner with cron-friendly options.",
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    subparsers.add_parser(
        "setup",
        help="Run the one-time visible-browser login flow.",
    )

    subparsers.add_parser(
        "connect",
        parents=[credential_parent],
        help="Send LinkedIn connection requests.",
    )

    subparsers.add_parser(
        "message",
        parents=[credential_parent],
        help="Send LinkedIn messages.",
    )

    cron_parser = subparsers.add_parser(
        "cron",
        parents=[credential_parent],
        help="Generate or install a crontab entry for connect/message.",
    )
    cron_parser.add_argument(
        "--task",
        choices=AUTOMATION_MODES,
        required=True,
        help="Automation task the cron job should run.",
    )
    cron_parser.add_argument(
        "--schedule",
        required=True,
        help='Cron schedule expression, for example "0 9 * * *" or "@daily".',
    )
    cron_parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python interpreter to use inside cron. Defaults to the current interpreter.",
    )
    cron_parser.add_argument(
        "--project-dir",
        default=BASE_DIR,
        help="Project directory to cd into before running the job.",
    )
    cron_parser.add_argument(
        "--log-file",
        help="File where cron stdout/stderr should be appended.",
    )
    cron_parser.add_argument(
        "--identifier",
        help="Unique marker used when installing or replacing the cron entry.",
    )
    cron_parser.add_argument(
        "--install",
        action="store_true",
        help="Install the generated entry into the current user's crontab.",
    )

    return parser


def _resolve_linkedin_credentials(args):
    """Resolve LinkedIn credentials from CLI arguments, env vars, or config defaults."""
    username = args.linkedin_username or os.getenv("LINKEDIN_USERNAME") or DEFAULT_USERNAME
    password = args.linkedin_password or os.getenv("LINKEDIN_PASSWORD") or DEFAULT_PASSWORD

    if not username:
        raise ValueError(
            "LinkedIn username is missing. Provide --linkedin-username or set LINKEDIN_USERNAME."
        )
    if password is None or password == "":
        raise ValueError(
            "LinkedIn password is missing. Provide --linkedin-password or set LINKEDIN_PASSWORD."
        )

    return username, password


def _validate_cron_schedule(schedule: str):
    """Validate a basic cron schedule expression."""
    schedule = (schedule or "").strip()
    if not schedule:
        raise ValueError("Cron schedule cannot be empty.")

    if schedule.startswith("@"):
        return schedule

    parts = schedule.split()
    if len(parts) != 5:
        raise ValueError(
            "Cron schedule must contain 5 fields (minute hour day month weekday) "
            'or use a shortcut such as "@daily".'
        )

    return schedule


def _default_log_file(task: str, project_dir: str) -> str:
    """Return a default log file path for cron runs."""
    return _join_target_path(project_dir, "logs", f"{task}.log")


def _looks_like_windows_path(path: str) -> bool:
    """Best-effort detection for Windows-style paths."""
    return bool(re.match(r"^[A-Za-z]:[\\/]", path)) or "\\" in path


def _target_path_module(path: str):
    """Choose a path module based on the target path style."""
    return ntpath if _looks_like_windows_path(path) else posixpath


def _join_target_path(base_path: str, *parts: str) -> str:
    """Join paths without forcing the current OS path separator semantics."""
    return _target_path_module(base_path).join(base_path, *parts)


def _dirname_target_path(path: str) -> str:
    """Return the directory name using the target path style."""
    return _target_path_module(path).dirname(path)


def _build_cron_entry(task: str, schedule: str, username: str, password: str,
                      python_bin: str, project_dir: str, log_file: str, identifier: str) -> str:
    """Build a shell-safe crontab entry."""
    main_path = _join_target_path(project_dir, "main.py")
    log_dir = _dirname_target_path(log_file) or "."

    env_prefix = " ".join(
        [
            "PYTHONUNBUFFERED=1",
            f"LINKEDIN_USERNAME={shlex.quote(username)}",
            f"LINKEDIN_PASSWORD={shlex.quote(password)}",
        ]
    )

    command = (
        f"mkdir -p {shlex.quote(log_dir)} && "
        f"cd {shlex.quote(project_dir)} && "
        f"{env_prefix} {shlex.quote(python_bin)} {shlex.quote(main_path)} "
        f"{shlex.quote(task)} >> {shlex.quote(log_file)} 2>&1"
    )

    return f"{schedule} {command} # {identifier}"


def _install_crontab_entry(entry: str, identifier: str):
    """Install or replace a crontab entry for the current user."""
    crontab_binary = shutil.which("crontab")
    if not crontab_binary:
        raise RuntimeError(
            "The 'crontab' command was not found on this machine. "
            "Generate the entry here and install it on the Linux host that runs cron."
        )

    current = subprocess.run(
        [crontab_binary, "-l"],
        capture_output=True,
        text=True,
        check=False,
    )

    if current.returncode not in (0, 1):
        error_text = current.stderr.strip() or current.stdout.strip() or "Unknown error."
        raise RuntimeError(f"Unable to read the current crontab: {error_text}")

    existing_lines = current.stdout.splitlines() if current.returncode == 0 else []
    filtered_lines = [line for line in existing_lines if identifier not in line]
    filtered_lines.append(entry)

    new_crontab = "\n".join(line for line in filtered_lines if line.strip()) + "\n"

    installed = subprocess.run(
        [crontab_binary, "-"],
        input=new_crontab,
        text=True,
        capture_output=True,
        check=False,
    )

    if installed.returncode != 0:
        error_text = installed.stderr.strip() or installed.stdout.strip() or "Unknown error."
        raise RuntimeError(f"Unable to install the crontab entry: {error_text}")


def _handle_cron_command(args):
    """Generate or install a cron entry."""
    username, password = _resolve_linkedin_credentials(args)
    schedule = _validate_cron_schedule(args.schedule)
    project_dir = args.project_dir
    log_file = args.log_file or _default_log_file(args.task, project_dir)
    identifier = args.identifier or f"linkedin-automation:{args.task}"

    entry = _build_cron_entry(
        task=args.task,
        schedule=schedule,
        username=username,
        password=password,
        python_bin=args.python_bin,
        project_dir=project_dir,
        log_file=log_file,
        identifier=identifier,
    )

    print("=" * 60)
    print("CRONTAB ENTRY")
    print("=" * 60)
    print(entry)
    if os.name == "nt":
        print()
        print(
            "WARNING: This entry was generated on Windows. "
            "For a Linux crontab, pass Linux-style values for --project-dir and --python-bin."
        )

    if args.install:
        _install_crontab_entry(entry, identifier)
        print()
        print("INFO: Crontab entry installed successfully.")
        print(f"INFO: Identifier: {identifier}")
        print(f"INFO: Log file: {log_file}")
    else:
        print()
        print("INFO: Copy this line into crontab -e, or rerun with --install on Linux.")
        print(f"INFO: Log file: {log_file}")


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
        "Tráº¡ng thÃ¡i káº¿t ná»‘i",
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
        status_col = "Tráº¡ng thÃ¡i káº¿t ná»‘i"
        df[status_col] = ""

    for index, row in df.iterrows():
        # Go to profile link.
        profile_link = str(row.get(link_col, "")).strip()
        if not profile_link:
            df.at[index, status_col] = "KhÃ´ng tá»“n táº¡i"
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


def _run_automation_mode(mode: str, username: str, password: str):
    """Run the connect/message automation flow."""
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
            login(driver, username, password)
        except LoginError as e:
            print(f"\nâŒ  FATAL: Cannot log in to LinkedIn: {e}")
            print("   Please run  'python main.py setup'  to log in manually first.")
            sys.exit(2)
        except SecurityChallengeError as e:
            print(f"\nâŒ  FATAL: Unresolvable security challenge: {e}")
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
        print("\n\nâš ï¸  Program interrupted by user.")
    except Exception as e:
        print(f"\nâŒ  Unexpected error: {e}")
        logging.exception("Unhandled exception in main():")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            print("INFO: Browser closed.")


def main():
    """Main function orchestrating the LinkedIn automation workflow."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode == "setup":
        setup_login()
        return

    if args.mode == "cron":
        _handle_cron_command(args)
        return

    username, password = _resolve_linkedin_credentials(args)
    _run_automation_mode(args.mode, username, password)


if __name__ == "__main__":
    main()
