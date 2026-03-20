# LinkedIn Automatic Add and Connect

This project is a Python/Selenium automation tool that reads leads from Google Sheets, opens LinkedIn profiles, sends connection requests or messages, and writes the result back to the sheet.

Warning: This project is for personal, educational, or internal use only and is not allowed for commercial purposes.

The repository is organized around a single CLI entry point:

```bash
python main.py <mode>
```

Available modes:

- `setup`
- `connect`
- `message`
- `cron`

## What this repo does

- Opens LinkedIn in Chrome with a persistent browser profile.
- Reads profile data from a Google Sheet.
- Sends connection requests or messages depending on the selected mode.
- Updates the status column back in the spreadsheet.
- Can generate or install a cron job for scheduled runs on Linux/macOS.

## Prerequisites

Before running anything, make sure you have:

- Python 3.8 or newer
- Google Chrome installed
- A working internet connection
- Access to a Google Cloud service account JSON key
- Access to a Google Sheet that contains the leads you want to process

If you are on Windows, the automation itself can run locally, but the `cron` mode is meant for Linux/macOS systems that have `crontab`.

## Project Files You Will Configure

The main files you usually need to touch are:

- [`config.py`](config.py): global settings such as Google Sheet ID, sheet name, Chrome profile path, and optional default LinkedIn credentials
- [`main.py`](main.py): the CLI entry point
- `credential/`: folder where the Google service account JSON file should live

## `config.py` Setup

If `config.py` is not included in your GitHub copy of this project, you need to create it manually before running the automation.

### 1. Create the file

Create a new file named `config.py` in the project root directory, next to `main.py`.

Your folder should look like this:

```text
LinkedIn-automatic-add-and-connect/
├─ main.py
├─ config.py
├─ requirements.txt
└─ credential/
```

### 2. Add the required settings

At minimum, `config.py` should contain the configuration values used by the code, including:

- `BASE_DIR`
- `USERNAME`
- `PASSWORD`
- `SPREADSHEET_ID`
- `SHEET_NAME`
- `RANGE_NAME`
- `KEYFILE_PATH`
- `WINDOW_SIZE`
- `CHROME_PROFILE_DIR`
- `MAX_LOGIN_RETRIES`
- `RETRY_BACKOFF_BASE`
- `SETUP_LOGIN_TIMEOUT`

### 3. Point the Google key path to your local file

Make sure `KEYFILE_PATH` points to the service account JSON file that exists on your machine.

Example:

```python
KEYFILE_PATH = os.path.join(BASE_DIR, "credential", "your-service-account.json")
```

### 4. Set your spreadsheet details

Update the spreadsheet-related values so they match your Google Sheet:

```python
SPREADSHEET_ID = "your_spreadsheet_id"
SHEET_NAME = "Sheet1"
RANGE_NAME = "A:E"
```

### 5. Save the file before running the project

After `config.py` is created and filled in, you can continue with the normal installation steps and run the CLI commands in [`main.py`](main.py).

## Installation

### 1. Clone or open the repository

Open the project folder in your terminal.

### 2. Create and activate a virtual environment

Recommended, but optional.

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

If installation fails because `pip` is outdated, upgrade it first:

```bash
python -m pip install --upgrade pip
```

## Google Sheets Setup

The script reads and writes data in Google Sheets, so this step is required.

### 1. Set up a Google Cloud Project & Enable APIs

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).
3. Navigate to **APIs & Services** > **Library**.
4. Search for the **Google Sheets API** and click **Enable**.
5. Go back to the Library, search for the **Google Drive API**, and click **Enable**.

### 2. Create a Service Account & Download the JSON Key

1. In the console, go to **APIs & Services** > **Credentials**.
2. Click **+ CREATE CREDENTIALS** and select **Service account**.
3. Enter a name, click **Create and Continue**, then click **Done**.
4. Click on the email address of the newly created service account in the list.
5. Go to the **Keys** tab, click **ADD KEY** > **Create new key**.
6. Select **JSON** and click **Create** to save the file to your computer.

Next, place the downloaded JSON file into the project's `credential/` folder.

Example:

```text
credential/your-service-account.json
```

### 3. Update `config.py`

Open [`config.py`](config.py) and confirm these values:

- `SPREADSHEET_ID`
- `SHEET_NAME`
- `RANGE_NAME`
- `KEYFILE_PATH`

`KEYFILE_PATH` must point to the JSON key you placed in `credential/`.

### 4. Share the spreadsheet with the service account

Open your Google Sheet and share it with the service account email address from the JSON file. Without this, the script will not be able to read or update the sheet.

## Google Sheet Format

The code tries to match column names in a flexible way, so the exact spelling does not have to be perfect. Still, using the suggested names below will make the setup easier.

### For `connect`

Required:

- `Link` or a similar name such as `Profile Link`, `Profile URL`, `URL`, `LinkedIn URL`

Optional:

- `Email` or `E-mail`

Status output:

- `Connection Status`

### For `message`

Required:

- `Link` or a similar name such as `Profile Link`, `Profile URL`, `URL`, `LinkedIn URL`
- `Name` or a similar name such as `Full Name`, `First Name`, `Contact Name`
- `Message` or a similar name such as `Msg`, `Template`, `Text`

Optional:

- `Attachment` or a similar name such as `File`, `Attachment File`

Status output:

- `Status`, `Result`, or `Message Status`

## LinkedIn Credentials

You can provide credentials in three ways:

1. Pass them directly on the command line with `--linkedin-username` and `--linkedin-password`
2. Set environment variables:

```powershell
$env:LINKEDIN_USERNAME="your-email@example.com"
$env:LINKEDIN_PASSWORD="your-password"
```

3. Set the defaults inside `config.py`

The command-line arguments override environment variables, and environment variables override the values in `config.py`.

## First-Time Run

The safest way to start is to perform the initial login setup first. This creates and reuses a real Chrome profile so the later automation runs are more stable.

### 1. Run setup

```bash
python main.py setup
```

What happens during setup:

- Chrome opens in visible mode
- The script tries to log in using the configured credentials
- You may need to complete LinkedIn security checks manually
- The browser profile is saved for future runs

### 2. Finish any challenge manually

If LinkedIn asks for:

- CAPTCHA
- email verification
- two-factor authentication
- suspicious login confirmation

complete it in the browser window during setup.

### 3. Wait for setup to finish

Once the profile is stored, future `connect` and `message` runs can reuse it.

## How to Run Each Mode

### 1. Connect Mode

This mode visits each profile in the sheet and sends a connection request.

Run it with:

```bash
python main.py connect
```

If you want to provide credentials directly:

```bash
python main.py connect --linkedin-username "YOUR_EMAIL" --linkedin-password "YOUR_PASSWORD"
```

What it does:

- Creates a Selenium driver
- Loads your Google Sheet
- Logs into LinkedIn
- Visits each profile link in the sheet
- Attempts the connection request
- Writes the result back to the status column

### 2. Message Mode

This mode sends a message to each target profile using the template in your sheet.

Run it with:

```bash
python main.py message
```

You can also pass credentials the same way as connect mode:

```bash
python main.py message --linkedin-username "YOUR_EMAIL" --linkedin-password "YOUR_PASSWORD"
```

What it does:

- Loads the sheet
- Validates that required message fields exist
- Opens each LinkedIn profile link
- Sends the prepared message
- Saves the result in the status column

### 3. Cron Mode

This mode helps you create a cron entry for scheduling on Linux/macOS systems so that the script runs automatically at specified times.

#### Option A: Install via Script (Recommended)

You can automatically add the cron job directly to your user's crontab using the `--install` flag:

```bash
# Install cron job to run the 'connect' task every day at 9:00 AM
python main.py cron --task connect --schedule "0 9 * * *" --install

# Install cron job to run the 'message' task every day at 10:00 AM
python main.py cron --task message --schedule "0 10 * * *" --install
```

If you just want to preview the cron line without installing it, omit the `--install` flag:

```bash
python main.py cron --task connect --schedule "0 9 * * *"
```

**Useful options:**
- `--task`: Either `connect` or `message`
- `--schedule`: A standard cron string like `"0 9 * * *"`
- `--python-bin`: The path to your Python interpreter (e.g., `/home/user/project/.venv/bin/python`)
- `--project-dir`: The absolute path to this project directory
- `--log-file`: The absolute path to a log file for capturing script output
- `--identifier`: A comment used to label and identify the cron entry

#### Option B: Manually Add to crontab

If you prefer to configure crontab manually yourself:

1. Open your crontab for editing:
   ```bash
   crontab -e
   ```
2. Add a new line specifying the schedule, the working directory, the path to your Python executable, and the task to run. For example, to run `connect` daily at 9:00 AM:
   ```bash
   0 9 * * * cd /path/to/LinkedIn-automatic-add-and-connect && /path/to/.venv/bin/python main.py connect >> logs/cron.log 2>&1
   ```
3. Save and close the editor to install the new cron job.

**Important notes:**
- `crontab` is for Linux/macOS. On Windows, use Task Scheduler.
- Make sure to use the absolute path to your virtual environment's Python executable if you installed dependencies in a `.venv`.
- If Selenium needs to open a visible browser window, you may need to specify the display variable (e.g., include `DISPLAY=:0 ` before the command) or configure Chrome to run in headless mode.

## Step-by-Step Example

If you want the shortest path from zero to working automation, follow this exact order:

1. Open the project folder.
2. Create and activate a virtual environment.
3. Install dependencies with `pip install -r requirements.txt`.
4. Put your Google service account JSON file inside `credential/`.
5. Update `config.py` with the correct spreadsheet ID, sheet name, range, and JSON file path.
6. Share the Google Sheet with the service account email.
7. Make sure your sheet has the required columns for the mode you want to run.
8. Run `python main.py setup`.
9. Finish any LinkedIn verification step in the browser if prompted.
10. Run `python main.py connect` or `python main.py message`.
11. Check the spreadsheet for the updated status values.

## Troubleshooting

### `Missing required column`

The sheet is missing a required header. Check the column names in the Google Sheet and make sure they match one of the supported names in this README.

### `Cannot log in to LinkedIn`

Usually this means:

- the username or password is wrong
- LinkedIn is asking for additional verification
- the saved Chrome profile is stale

Run `python main.py setup` again and complete the login manually if needed.

### `The 'crontab' command was not found`

You are probably on Windows or on a Linux system without cron installed. Generate the entry and add it on a machine that supports `crontab`.

### Google Sheets is not updating

Check that:

- the service account JSON file exists at `KEYFILE_PATH`
- the sheet is shared with the service account
- the sheet ID and sheet name in `config.py` are correct

## Logging and Output

During normal runs, the script prints progress to the console.

Additional output may include:

- screenshots saved in the project root
- log files created under `logs/` when using cron mode

## Notes

- This project depends on Selenium and a persistent Chrome profile.
- The exact status text written back to Google Sheets may vary depending on the branch of the workflow.
- If you modify the sheet structure, update the README and `config.py` together so the automation stays aligned.