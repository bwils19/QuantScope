# inital historical data load
import datetime
from typing import List
from backend import db


async def initial_data_load(tickers: List[str]):
    """Perform initial historical data load"""
    try:
        print(f"Starting initial data load for {len(tickers)} tickers")

        # Get existing data
        existing_tickers = set(db.session.query(
            SecurityHistoricalData.ticker
        ).distinct().all())

        # Filter for new tickers
        new_tickers = [t for t in tickers if t not in existing_tickers]

        if not new_tickers:
            print("No new tickers to load")
            return

        # Process in batches
        batch_size = 5  # Adjust based on API limits
        end_date = datetime.now()
        start_date = end_date - datetime.timedelta(days=365 * 2)  # 2 years of data

        results = await process_historical_data_batch(
            new_tickers,
            start_date,
            end_date,
            batch_size
        )

        # Validate and save data
        for ticker, data in results.items():
            if not data:
                continue

            clean_data = HistoricalDataValidator.clean_data(data)
            await cache_historical_data(ticker, clean_data)

        print(f"Completed initial load for {len(results)} tickers")

    except Exception as e:
        print(f"Error in initial data load: {e}")
