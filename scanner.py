import os
import json
import pandas as pd
import yfinance as yf
import gspread
import time
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
    "Raw_Nifty50": "^NSEI",
    "Raw_BankNifty": "^NSEBANK",
    "Raw_IT": "^CNXIT",
    "Raw_Auto": "^CNXAUTO",
    "Raw_FMCG": "^CNXFMCG",
    "Raw_Pharma": "^CNXPHARMA",
    "Raw_Metal": "^CNXMETAL",
    "Raw_Realty": "^CNXREALTY",
    "Raw_FinancialServices": "NIFTY_FIN_SERVICE.NS",
    "Raw_PSUBank": "^CNXPSUBANK"
}

# ==========================================
# DOWNLOAD & UPDATE RAW SHEETS
# ==========================================

for sheet_name, ticker in indices.items():
    print(f"Processing {sheet_name}")

    try:
        df = yf.download(
            ticker,
            period="10y",
            interval="1mo",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if df.empty:
            print(f"No data found for {ticker}")
            continue

        df.reset_index(inplace=True)
        print(df.tail())
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
            
           
        # Remove future dates

        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce"
        )
        
        current_year = pd.Timestamp.today().year
        
        df = df[
            df["Date"].dt.year <= current_year
        ]
        
        if "Volume" in df.columns:
            df = df[df["Volume"] > 0]
        
        df = df.sort_values("Date")
       
        today = pd.Timestamp.today()

        df = df[
            df["Date"] <= today
        ]   
        
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

        ws.update(
            values=data,
            range_name="A1"
        )

        print(f"{sheet_name} updated successfully")
        time.sleep(2)
        
    except Exception as e:
        print(f"Error processing {sheet_name}")
        print(str(e))

# ==========================================
# SEASONALITY MATRIX
# ==========================================

try:
    ws_raw = spreadsheet.worksheet("Raw_Nifty50")
    raw_data = ws_raw.get_all_values()

    season_df = pd.DataFrame(
        raw_data[1:],
        columns=raw_data[0]
    )

    season_df["Date"] = pd.to_datetime(
        season_df["Date"]
    )

    season_df["Return %"] = pd.to_numeric(
        season_df["Return %"],
        errors="coerce"
    )

    season_df["Year"] = season_df["Date"].dt.year
    season_df["Month"] = season_df["Date"].dt.strftime("%b")

    # Remove first partial year and current year
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

    month_order = [
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec"
    ]

    matrix = season_df.pivot_table(
        index="Year",
        columns="Month",
        values="Return %",
        aggfunc="first"
    )

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
# ==========================================
# SECTOR RANKING ENGINE
# ==========================================

try:

    sector_results = []

    sector_sheets = [
        "Raw_Nifty50",
        "Raw_BankNifty",
        "Raw_IT",
        "Raw_Auto",
        "Raw_FMCG",
        "Raw_Pharma",
        "Raw_Metal",
        "Raw_Realty",
        "Raw_FinancialServices",
        "Raw_PSUBank"
    ]

    for sector in sector_sheets:

        try:

            ws_sector = spreadsheet.worksheet(sector)

            data = ws_sector.get_all_values()

            if len(data) <= 1:
                continue

            df_sector = pd.DataFrame(
                data[1:],
                columns=data[0]
            )

            df_sector["Return %"] = pd.to_numeric(
                df_sector["Return %"],
                errors="coerce"
            )

            avg_return = round(
                df_sector["Return %"].mean(),
                2
            )

            win_rate = round(
                (
                    (df_sector["Return %"] > 0).sum()
                    /
                    df_sector["Return %"].count()
                ) * 100,
                2
            )

            sector_results.append([
                sector.replace("Raw_", ""),
                avg_return,
                win_rate
            ])

        except Exception as e:
            print(f"Sector Error: {sector}")
            print(str(e))

    ranking_df = pd.DataFrame(
        sector_results,
        columns=[
            "Sector",
            "Avg Return",
            "Win Rate %"
        ]
    )

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
        ws_sector_rank = spreadsheet.worksheet(
            "Sector_Ranking_V2"
        )
    except:
        ws_sector_rank = spreadsheet.add_worksheet(
            title="Sector_Ranking_V2",
            rows=50,
            cols=10
        )

    ws_sector_rank.clear()

    sector_data = [
        ranking_df.columns.tolist()
    ] + ranking_df.values.tolist()

    ws_sector_rank.update(
        values=sector_data,
        range_name="A1"
    )

    print("Sector Ranking Updated")

except Exception as e:
    print("Sector Ranking Error")
    print(str(e))
 # ==========================================
# SECTOR MOMENTUM ENGINE
# ==========================================

try:

    momentum_results = []

    sector_sheets = [
        "Raw_Nifty50",
        "Raw_BankNifty",
        "Raw_IT",
        "Raw_Auto",
        "Raw_FMCG",
        "Raw_Pharma",
        "Raw_Metal",
        "Raw_Realty",
        "Raw_FinancialServices",
        "Raw_PSUBank"
    ]

    for sector in sector_sheets:

        try:

            ws_sector = spreadsheet.worksheet(sector)

            data = ws_sector.get_all_values()

            if len(data) <= 7:
                continue

            df_sector = pd.DataFrame(
                data[1:],
                columns=data[0]
            )

            df_sector["Close"] = pd.to_numeric(
                df_sector["Close"],
                errors="coerce"
            )
            df_sector["Date"] = pd.to_datetime(
                df_sector["Date"],
                errors="coerce"
            )
            
            df_sector = df_sector.sort_values(
                by="Date"
            )
            
            today = pd.Timestamp.today()
            
            df_sector = df_sector[
                df_sector["Date"] <= today
            ]
            
            df_sector = df_sector.dropna()

            latest_close = df_sector["Close"].iloc[-1]

            close_3m = df_sector["Close"].iloc[-4]

            close_6m = df_sector["Close"].iloc[-7]

            return_3m = round(
                ((latest_close / close_3m) - 1) * 100,
                2
            )

            return_6m = round(
                ((latest_close / close_6m) - 1) * 100,
                2
            )

            momentum_results.append([
                sector.replace("Raw_", ""),
                return_3m,
                return_6m
            ])

        except Exception as e:
            print(f"Momentum Error: {sector}")
            print(str(e))

    momentum_df = pd.DataFrame(
        momentum_results,
        columns=[
            "Sector",
            "3M Return %",
            "6M Return %"
        ]
    )

    momentum_df = momentum_df.sort_values(
        by="3M Return %",
        ascending=False
    )

    momentum_df.insert(
        0,
        "Rank",
        range(1, len(momentum_df) + 1)
    )

    try:
        ws_momentum = spreadsheet.worksheet(
            "Sector_Momentum_V2"
        )
    except:
        ws_momentum = spreadsheet.add_worksheet(
            title="Sector_Momentum_V2",
            rows=50,
            cols=10
        )

    ws_momentum.clear()

    momentum_data = [
        momentum_df.columns.tolist()
    ] + momentum_df.values.tolist()

    ws_momentum.update(
        values=momentum_data,
        range_name="A1"
    )

    print("Sector Momentum Updated")

except Exception as e:
    print("Sector Momentum Error")
    print(str(e))  
    
# ==========================================
# AI SECTOR SCORE ENGINE
# ==========================================

try:

    # Read Sector Ranking
    ws_rank = spreadsheet.worksheet(
        "Sector_Ranking_V2"
    )

    rank_data = ws_rank.get_all_values()

    rank_df = pd.DataFrame(
        rank_data[1:],
        columns=rank_data[0]
    )

    # Read Momentum Ranking
    ws_momentum = spreadsheet.worksheet(
        "Sector_Momentum_V2"
    )

    momentum_data = ws_momentum.get_all_values()

    momentum_df = pd.DataFrame(
        momentum_data[1:],
        columns=momentum_data[0]
    )

    # Convert numeric fields

    rank_df["Avg Return"] = pd.to_numeric(
        rank_df["Avg Return"],
        errors="coerce"
    )

    rank_df["Win Rate %"] = pd.to_numeric(
        rank_df["Win Rate %"],
        errors="coerce"
    )

    momentum_df["3M Return %"] = pd.to_numeric(
        momentum_df["3M Return %"],
        errors="coerce"
    )

    # Merge

    ai_df = pd.merge(
        rank_df,
        momentum_df[[
            "Sector",
            "3M Return %"
        ]],
        on="Sector",
        how="inner"
    )

    # Normalize Scores

    ai_df["Seasonality Score"] = (
        ai_df["Avg Return"].rank(
            pct=True
        ) * 100
    )

    ai_df["Momentum Score"] = (
        ai_df["3M Return %"].rank(
            pct=True
        ) * 100
    )

    ai_df["Win Score"] = (
        ai_df["Win Rate %"].rank(
            pct=True
        ) * 100
    )

    # Final AI Score

    ai_df["AI Score"] = (
        ai_df["Seasonality Score"] * 0.40
        +
        ai_df["Momentum Score"] * 0.40
        +
        ai_df["Win Score"] * 0.20
    ).round(2)

    ai_df = ai_df.sort_values(
        by="AI Score",
        ascending=False
    )

    if "Rank" in ai_df.columns:
        del ai_df["Rank"]

    ai_df.insert(
        0,
        "Rank",
        range(1, len(ai_df) + 1)
    )

    final_df = ai_df[[
        "Rank",
        "Sector",
        "AI Score",
        "Avg Return",
        "3M Return %",
        "Win Rate %"
    ]]

    try:
        ws_ai = spreadsheet.worksheet(
            "AI_Sector_Score"
        )
    except:
        ws_ai = spreadsheet.add_worksheet(
            title="AI_Sector_Score",
            rows=50,
            cols=20
        )

    ws_ai.clear()

    ai_data = [
        final_df.columns.tolist()
    ] + final_df.values.tolist()

    ws_ai.update(
        values=ai_data,
        range_name="A1"
    )

    print("AI Sector Score Updated")

except Exception as e:
    print("AI Sector Score Error")
    print(str(e))
 # ==========================================
# DASHBOARD V2
# ==========================================

try:

    # Read AI Score Sheet
    ws_ai = spreadsheet.worksheet(
        "AI_Sector_Score"
    )

    ai_data = ws_ai.get_all_values()

    ai_df = pd.DataFrame(
        ai_data[1:],
        columns=ai_data[0]
    )

    # Read Best Month Ranking
    ws_month = spreadsheet.worksheet(
        "Best_Month_Ranking"
    )

    month_data = ws_month.get_all_values()

    month_df = pd.DataFrame(
        month_data[1:],
        columns=month_data[0]
    )

    # Read Momentum Sheet
    ws_momentum = spreadsheet.worksheet(
        "Sector_Momentum_V2"
    )

    momentum_data = ws_momentum.get_all_values()

    momentum_df = pd.DataFrame(
        momentum_data[1:],
        columns=momentum_data[0]
    )

    # Top Sector

    best_sector = ai_df.iloc[0]["Sector"]
    best_score = ai_df.iloc[0]["AI Score"]

    # Best Month

    best_month = month_df.iloc[0]["Month"]

    # Highest Momentum

    highest_momentum_sector = (
        momentum_df.iloc[0]["Sector"]
    )

    highest_momentum = (
        momentum_df.iloc[0]["3M Return %"]
    )

    # Dashboard Data

    dashboard = [
        ["Metric", "Value"],
        ["Best Sector", best_sector],
        ["AI Score", best_score],
        ["Best Month", best_month],
        ["Highest Momentum Sector", highest_momentum_sector],
        ["Highest 3M Return %", highest_momentum],
        [],
        ["Top 5 Sector Leaderboard"],
        ["Rank", "Sector", "AI Score"]
    ]

    top5 = ai_df.head(5)

    for _, row in top5.iterrows():

        dashboard.append([
            row["Rank"],
            row["Sector"],
            row["AI Score"]
        ])

    dashboard.append([])

    dashboard.append(
        ["Suggested Allocation"]
    )

    dashboard.append(
        ["Sector", "Weight %"]
    )

    dashboard.append(
        [best_sector, 35]
    )

    if len(ai_df) > 1:
        dashboard.append(
            [ai_df.iloc[1]["Sector"], 25]
        )

    if len(ai_df) > 2:
        dashboard.append(
            [ai_df.iloc[2]["Sector"], 20]
        )

    if len(ai_df) > 3:
        dashboard.append(
            [ai_df.iloc[3]["Sector"], 10]
        )

    dashboard.append(
        ["Cash", 10]
    )

    try:
        ws_dash = spreadsheet.worksheet(
            "Dashboard_V2"
        )
    except:
        ws_dash = spreadsheet.add_worksheet(
            title="Dashboard_V2",
            rows=100,
            cols=20
        )

    ws_dash.clear()

    ws_dash.update(
        values=dashboard,
        range_name="A1"
    )

    print("Dashboard Updated")

except Exception as e:
    print("Dashboard Error")
    print(str(e))
    
    # ==========================================
# RELATIVE STRENGTH ENGINE
# ==========================================

try:

    ws_momentum = spreadsheet.worksheet(
        "Sector_Momentum_V2"
    )

    momentum_data = ws_momentum.get_all_values()

    rs_df = pd.DataFrame(
        momentum_data[1:],
        columns=momentum_data[0]
    )

    rs_df["6M Return %"] = pd.to_numeric(
        rs_df["6M Return %"],
        errors="coerce"
    )

    # Nifty Return

    nifty_return = rs_df[
        rs_df["Sector"] == "Nifty50"
    ]["6M Return %"].iloc[0]

    rs_results = []

    for _, row in rs_df.iterrows():

        sector = row["Sector"]

        sector_return = row["6M Return %"]

        if nifty_return == 0:
            rs_score = 0
        else:
            rs_score = round(
                sector_return / nifty_return,
                2
            )

        rs_results.append([
            sector,
            sector_return,
            rs_score
        ])

    final_rs = pd.DataFrame(
        rs_results,
        columns=[
            "Sector",
            "6M Return %",
            "RS Score"
        ]
    )

    final_rs = final_rs.sort_values(
        by="RS Score",
        ascending=False
    )

    final_rs.insert(
        0,
        "Rank",
        range(1, len(final_rs) + 1)
    )

    try:
        ws_rs = spreadsheet.worksheet(
            "Sector_RS_V2"
        )
    except:
        ws_rs = spreadsheet.add_worksheet(
            title="Sector_RS_V2",
            rows=50,
            cols=10
        )

    ws_rs.clear()

    rs_data = [
        final_rs.columns.tolist()
    ] + final_rs.values.tolist()

    ws_rs.update(
        values=rs_data,
        range_name="A1"
    )

    print("Relative Strength Updated")

except Exception as e:
    print("RS Engine Error")
    print(str(e))
print("Google Sheet Updated Successfully")
