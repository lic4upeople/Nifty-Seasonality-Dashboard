import os
import json
import pandas as pd
import yfinance as yf
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# GOOGLE SHEET CONNECTION

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

# INDEX LIST

indices = {
   "Raw_Nifty50": "^NSEI",
   "Raw_BankNifty": "^NSEBANK"
}

# DOWNLOAD & UPDATE SHEET

for sheet_name, ticker in indices.items():

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

        # Flatten MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]

        df["Return %"] = (
        df["Close"].pct_change() * 100
        ).round(2)

        df["Close"] = df["Close"].round(2)

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

        data = [["Date", "Close", "Return %"]]

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
# ==========================================
# SEASONALITY MATRIX - NIFTY50
# ==========================================

try:

    ws_raw = spreadsheet.worksheet("Raw_Nifty50")

    raw_data = ws_raw.get_all_values()

    season_df = pd.DataFrame(
        raw_data[1:],
        columns=raw_data[0]
    )

    season_df["Date"] = pd.to_datetime(season_df["Date"])

    season_df["Return %"] = pd.to_numeric(
        season_df["Return %"],
        errors="coerce"
    )

    season_df["Year"] = season_df["Date"].dt.year

    season_df["Month"] = season_df["Date"].dt.strftime("%b")
current_year = pd.Timestamp.today().year

all_years = sorted(
    season_df["Year"].unique()
)

first_year = all_years[0]

season_df = season_df[
    (season_df["Year"] != first_year)
    &
    (season_df["Year"] != current_year)
]
    matrix = season_df.pivot_table(
        index="Year",
        columns="Month",
        values="Return %",
        aggfunc="first"
    )

    month_order = [
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec"
    ]

    matrix = matrix.reindex(
        columns=month_order
    )

    matrix = matrix.round(2)

    matrix.reset_index(inplace=True)

    try:
        ws_season = spreadsheet.worksheet(
            "Sector_Seasonality"
        )
    except:
        ws_season = spreadsheet.add_worksheet(
            title="Sector_Seasonality",
            rows=100,
            cols=20
        )

    ws_season.clear()

    season_data = [
        matrix.columns.tolist()
    ] + matrix.fillna("").values.tolist()

    ws_season.update(
        values=season_data,
        range_name="A1"
    )

    print("Seasonality Matrix Updated")

except Exception as e:
    print("Seasonality Error")
    print(str(e))
    # ==========================================
# SEASONALITY STATS
# ==========================================

try:

    stats = []

    for month in month_order:

        values = pd.to_numeric(
            matrix[month],
            errors="coerce"
        )

        avg_return = round(
            values.mean(),
            2
        )

        positive_count = (
            values > 0
        ).sum()

        total_count = values.count()

        win_rate = round(
            (positive_count / total_count) * 100,
            2
        ) if total_count > 0 else 0

        stats.append([
            month,
            avg_return,
            win_rate
        ])

    stats_df = pd.DataFrame(
        stats,
        columns=[
            "Month",
            "Avg Return",
            "Win Rate %"
        ]
    )

    try:
        ws_stats = spreadsheet.worksheet(
            "Seasonality_Stats"
        )
    except:
        ws_stats = spreadsheet.add_worksheet(
            title="Seasonality_Stats",
            rows=50,
            cols=10
        )

    ws_stats.clear()

    stats_data = [
        stats_df.columns.tolist()
    ] + stats_df.values.tolist()

    ws_stats.update(
        values=stats_data,
        range_name="A1"
    )

    print("Seasonality Stats Updated")

except Exception as e:
    print("Seasonality Stats Error")
    print(str(e))
    # ==========================================
# BEST MONTH RANKING
# ==========================================

try:

    ranking_df = stats_df.copy()

    ranking_df = ranking_df.sort_values(
        by="Avg Return",
        ascending=False
    )

    ranking_df.insert(
        0,
        "Rank",
        range(1, len(ranking_df) + 1)
    )

    try:
        ws_rank = spreadsheet.worksheet(
            "Best_Month_Ranking"
        )
    except:
        ws_rank = spreadsheet.add_worksheet(
            title="Best_Month_Ranking",
            rows=50,
            cols=10
        )

    ws_rank.clear()

    ranking_data = [
        ranking_df.columns.tolist()
    ] + ranking_df.values.tolist()

    ws_rank.update(
        values=ranking_data,
        range_name="A1"
    )

    print("Best Month Ranking Updated")

except Exception as e:
    print("Best Month Ranking Error")
    print(str(e))
    
print("Google Sheet Updated Successfully")
