# -*- coding: utf-8 -*-
"""Google Sheets connection and data handling for LinkedIn automation."""

import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import SPREADSHEET_ID, SHEET_NAME, RANGE_NAME, KEYFILE_URL, KEYFILE_PATH
from support import download_file


def connect_google_sheet():
    """Authenticate and connect to Google Sheets, returning the sheet and DataFrame."""
    # Download the keyfile if it doesn't exist locally.
    download_file(KEYFILE_URL, KEYFILE_PATH)

    # Authenticate with Google Sheets API.
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(KEYFILE_PATH, scope)
    client = gspread.authorize(creds)

    # Get data from the spreadsheet.
    sheet = client.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
    values = sheet.get_all_values()
    df = pd.DataFrame(values[1:], columns=values[0])

    print(df)
    return sheet, df


def update_google_sheet(sheet, df):
    """Update the Google Sheet with the current DataFrame values."""
    updated_values = [df.columns.tolist()] + df.values.tolist()
    sheet.update(RANGE_NAME, updated_values)
