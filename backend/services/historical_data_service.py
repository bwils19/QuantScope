from backend import db
from backend.models import SecurityHistoricalData, Security
from datetime import datetime, timedelta
import requests
import time
import os


class HistoricalDataService:
    def __init__(self):
        self.api_key = os.getenv('ALPHA_VANTAGE_KEY')

    async def fetch_historical_data(self, ticker, start_date=None, end_date=None):
        """Fetch historical data for a ticker"""
        try:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TIME_SERIES_DAILY_ADJUSTED&"
                f"symbol={ticker}&outputsize=full&"
                f"apikey={self.api_key}"
            )
            response = requests.get(url)
            data = response.json()

            if 'Time Series (Daily)' not in data:
                print(f"No data found for {ticker}")
                return None

            processed_data = []
            time_series = data['Time Series (Daily)']

            for date_str, values in time_series.items():
                date = datetime.strptime(date_str, '%Y-%m-%d').date()

                if start_date and date < start_date:
                    continue
                if end_date and date > end_date:
                    continue

                processed_data.append({
                    'date': date,
                    'open_price': float(values['1. open']),
                    'high_price': float(values['2. high']),
                    'low_price': float(values['3. low']),
                    'close_price': float(values['4. close']),
                    'adjusted_close': float(values['5. adjusted close']),
                    'volume': int(values['6. volume'])
                })

            return processed_data

        except Exception as e:
            print(f"Error fetching historical data for {ticker}: {e}")
            return None

    async def update_historical_data(self):
        """Update historical data for all active securities"""
        try:
            # Get all unique tickers from securities table
            tickers = db.session.query(Security.ticker).distinct().all()
            tickers = [t[0] for t in tickers]

            for ticker in tickers:
                # Get latest date for this ticker
                latest_record = (
                    SecurityHistoricalData.query
                    .filter_by(ticker=ticker)
                    .order_by(SecurityHistoricalData.date.desc())
                    .first()
                )

                if latest_record:
                    start_date = latest_record.date + timedelta(days=1)
                else:
                    # First time pulling data for this ticker
                    start_date = (datetime.now() - timedelta(days=365 * 2)).date()
                end_date = datetime.now().date()

                if start_date > end_date:
                    continue  # already up to date

                data = await self.fetch_historical_data(ticker, start_date, end_date)
                if data:
                    for record in data:
                        hist_data = SecurityHistoricalData(
                            ticker=ticker,
                            **record
                        )
                        db.session.merge(hist_data)

                    await db.session.commit()

                time.sleep(10)  # this is what i need to adjust if i'm hitting api limits

        except Exception as e:
            print(f"Error in update_historical_data: {e}")
            db.session.rollback()
