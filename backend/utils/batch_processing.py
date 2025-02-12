# backend/utils/batch_processing.py
from typing import List, Dict
import asyncio
from datetime import datetime, timedelta


async def process_historical_data_batch(
        tickers: List[str],
        start_date: datetime,
        end_date: datetime,
        batch_size: int = 10
) -> Dict:
    """Process historical data in batches"""
    results = {}

    # Split tickers into batches
    ticker_batches = [tickers[i:i + batch_size]
                      for i in range(0, len(tickers), batch_size)]

    for batch in ticker_batches:
        tasks = []
        for ticker in batch:
            task = asyncio.create_task(
                fetch_historical_data(ticker, start_date, end_date)
            )
            tasks.append(task)

        # Wait for batch to complete
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for ticker, result in zip(batch, batch_results):
            if isinstance(result, Exception):
                print(f"Error processing {ticker}: {result}")
                continue
            results[ticker] = result

        # Rate limiting between batches
        await asyncio.sleep(10)  # start this at 10 secs, but not sure it's necessary given my premium plan

    return results