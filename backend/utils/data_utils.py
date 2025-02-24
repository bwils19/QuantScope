import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from flask import current_app
from backend.models import StressScenario
from backend import db

stress_scenarios = [
    {"name": "2008_Crisis", "start": "2007-10-01", "end": "2009-03-31"},
    {"name": "COVID_Crash", "start": "2020-02-12", "end": "2020-03-23"},
    {"name": "2022_Inflation", "start": "2022-01-03", "end": "2022-10-12"},
    {"name": "DotCom_Bust", "start": "2000-03-10", "end": "2002-10-09"}
]

# Tickers for indices and sectors
tickers = {
    "S&P_500": "^GSPC",
    "Nasdaq": "^IXIC",
    "VIX": "^VIX",
    "Tech": "XLK",
    "Life_Sciences": "XLV",
    "Energy": "XLE"
}


def get_vix_baseline(start_date, months_before=12):
    baseline_end = datetime.strptime(start_date, "%Y-%m-%d") - pd.offsets.MonthEnd(months_before)
    baseline_start = baseline_end - pd.offsets.MonthEnd(0)
    df = yf.download("^VIX", start=baseline_start.strftime("%Y-%m-%d"), end=baseline_end.strftime("%Y-%m-%d"),
                     auto_adjust=False)
    return df['Close'].mean() if not df['Close'].isna().all().item() else 15  # Default to 15 if no data


# Function to fetch and process historical data for scenarios, accepting app instance
def fetch_and_process_stress_scenarios(app=None):
    if app is None:
        raise ValueError("App instance must be provided to fetch_and_process_stress_scenarios")

    with app.app_context():  # Use the provided app context
        for scenario in stress_scenarios:
            data = {}
            for name, ticker in tickers.items():
                try:
                    # Fetch historical data with unadjusted prices
                    df = yf.download(ticker, start=scenario["start"], end=scenario["end"], auto_adjust=False)
                    if not df.empty and 'Close' in df.columns:
                        # Get the first and trough valid closing prices, handling NaN
                        valid_closes = df['Close'].dropna()
                        if not valid_closes.empty:
                            start_close = valid_closes.iloc[0].item()  # First valid close
                            trough_close = valid_closes.min().item()  # Minimum close (trough)
                        else:
                            # Fallback to raw Close column if no valid data after dropping NaN
                            start_close = df['Close'].iloc[0] if not pd.isna(df['Close'].iloc[0]) else 0
                            trough_close = df['Close'].min() if not pd.isna(df['Close'].min()) else 0

                        # Calculate percentage change (peak to trough)
                        if isinstance(start_close, (int, float)) and start_close != 0:
                            price_change = ((trough_close - start_close) / start_close) * 100
                        else:
                            price_change = 0

                        # Calculate daily returns for volatility
                        df['Returns'] = df['Close'].pct_change()
                        # Calculate volatility (standard deviation of returns, annualized)
                        volatility = df['Returns'].std() * np.sqrt(252) if not df['Returns'].dropna().empty else 0

                        # For VIX, calculate shift from baseline to peak
                        if name == "VIX":
                            # Check if 'Close' column is all NaN using a safe scalar check
                            if df['Close'].isna().all().item() if not df['Close'].isna().all().empty else False:
                                vix_peak = 0
                                vix_avg = 0
                            else:
                                # Ensure max and mean are scalars, handle NaN and Series
                                vix_max = df['Close'].max()
                                if isinstance(vix_max, pd.Series):
                                    vix_max = vix_max.item() if not vix_max.empty and len(vix_max) == 1 else 0
                                vix_peak = vix_max if not pd.isna(vix_max) else 0

                                vix_mean = df['Close'].mean()
                                if isinstance(vix_mean, pd.Series):
                                    vix_mean = vix_mean.item() if not vix_mean.empty and len(vix_mean) == 1 else 0
                                vix_avg = vix_mean if not pd.isna(vix_mean) else 0
                            baseline_vix = get_vix_baseline(scenario["start"])
                            vix_shift = ((vix_peak - baseline_vix) / baseline_vix) * 100 if baseline_vix != 0 else 0
                        else:
                            vix_shift = 0

                        data[name] = {
                            "price_change_pct": price_change,
                            "volatility": volatility,
                            "vix_shift_pct": vix_shift,
                            "start_date": scenario["start"],
                            "end_date": scenario["end"]
                        }
                except Exception as e:
                    print(f"Error processing {ticker} for {scenario['name']}: {e}")
                    continue  # Skip this ticker/scenario and move to the next

            # Save to SQLite
            for index_name, metrics in data.items():
                try:
                    existing = StressScenario.query.filter_by(
                        event_name=scenario["name"],
                        index_name=index_name
                    ).first()
                    if not existing:
                        new_scenario = StressScenario(
                            event_name=scenario["name"],
                            index_name=index_name,
                            price_change_pct=metrics["price_change_pct"],
                            volatility=metrics["volatility"],
                            vix_shift_pct=metrics["vix_shift_pct"],
                            start_date=datetime.strptime(metrics["start_date"], "%Y-%m-%d").date(),
                            end_date=datetime.strptime(metrics["end_date"], "%Y-%m-%d").date()
                        )
                        db.session.add(new_scenario)
                except Exception as e:
                    print(f"Error saving {scenario['name']} - {index_name} to SQLite: {e}")
                    continue
            try:
                db.session.commit()
                print(f"Processed and stored data for {scenario['name']} in SQLite")
            except Exception as e:
                print(f"Error committing to SQLite for {scenario['name']}: {e}")
                db.session.rollback()
