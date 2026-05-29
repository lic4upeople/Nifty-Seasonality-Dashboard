import os
import json
import pandas as pd
import yfinance as yf
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -----------------------------
# GOOGLE SHEET CONNECTION
# -----------------------------

creds_json = os.environ.get("GCP_CREDENTIALS")

if not creds_json:
    raise Exception("GCP_CREDENTIALS secret not found")

creds_dict = json.loads(creds_json)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(
    creds_dict,
    scope
)

client = gspread.authorize(creds)

sheet_id = os.environ.get("SHEET_ID")

spreadsheet = client.open_by_key(sheet_id)

# -----------------------------
# INDEX LIST
# -----------------------------

indices = {
    "Nifty50": "^NSEI"
}

# -----------------------------
# DOWNLOAD DATA
# -----------------------------

for sheet_name, ticker in indices.items():

    print(f"Processing {sheet_name}")

    df = yf.download(
        ticker,
        period="10y",
        interval="1mo",
        auto_adjust=True
    )

    if df.empty:
        print(f"No data found for {ticker}")
        continue

    df.reset_index(inplace=True)

    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.strftime("%b")

    df["Return %"] = (
        df["Close"].pct_change() * 100
    ).round(2)

    result = df[["Date", "Close", "Return %"]]

    try:
        ws = spreadsheet.worksheet(sheet_name)
    except:
        ws = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=20
        )

    ws.clear()

    ws.update(
        [result.columns.values.tolist()]
        + result.values.tolist()
    )

print("Google Sheet Updated Successfully")
