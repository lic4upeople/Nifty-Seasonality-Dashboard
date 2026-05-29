import os
import json
import pandas as pd
import yfinance as yf
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================

# GOOGLE SHEET CONNECTION

# ==========================================

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

if not sheet_id:
raise Exception("SHEET_ID secret not found")

spreadsheet = client.open_by_key(sheet_id)

# ==========================================

# INDEX LIST

# ==========================================

indices = {
"Nifty50": "^NSEI"
}

# ==========================================

# DOWNLOAD & UPDATE SHEET

# ==========================================

for sheet_name, ticker in indices.items():

```
print(f"Processing {sheet_name}")

try:

    df = yf.download(
        ticker,
        period="10y",
        interval="1mo",
        auto_adjust=True,
        progress=False
    )

    if df.empty:
        print(f"No data found for {ticker}")
        continue

    df.reset_index(inplace=True)

    # Handle MultiIndex columns from yfinance
    new_cols = []
    for col in df.columns:
        if isinstance(col, tuple):
            new_cols.append(col[0])
        else:
            new_cols.append(col)

    df.columns = new_cols

    df["Return %"] = (
        df["Close"].pct_change() * 100
    ).round(2)

    result = df[["Date", "Close", "Return %"]].copy()

    result["Date"] = pd.to_datetime(
        result["Date"]
    ).dt.strftime("%Y-%m-%d")

    result = result.fillna("")
    result = result.astype(str)

    try:
        ws = spreadsheet.worksheet(sheet_name)
    except:
        ws = spreadsheet.add_worksheet(
            title=sheet_name,
            rows=1000,
            cols=20
        )

    ws.clear()

    data = []
    data.append(["Date", "Close", "Return %"])

    for row in result.values.tolist():
        data.append(row)

    print("Rows Found:", len(data))

    ws.update(
        values=data,
        range_name="A1"
    )

    print(f"{sheet_name} updated successfully")

except Exception as e:
    print(f"Error processing {sheet_name}")
    print(str(e))

print("Google Sheet Updated Successfully")
