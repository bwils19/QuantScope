from typing import Dict, List, Tuple, Any
import random
from backend import db
from backend.models import SecurityHistoricalData
from datetime import datetime, timedelta, date  
import os
import requests


def fetch_historical_prices(ticker: str) -> List[Tuple[date, float]]:
    """
    Fetch historical price data from our database, with API fallback for recent data
    """
    print(f"Starting fetch for {ticker}")
    try:
        historical_data = db.session.query(
            SecurityHistoricalData
        ).filter_by(
            ticker=ticker
        ).order_by(
            SecurityHistoricalData.date.desc()
        ).all()

        if not historical_data:
            print(f"No historical data found in database for {ticker}")
            return []

        # Convert to list of (date, price) tuples
        price_data = [(data.date, float(data.close_price))
                      for data in historical_data
                      if data.close_price is not None]

        # Check if we need more recent data
        if price_data:
            latest_date = price_data[0][0]
            today = date.today()

            if latest_date < today - timedelta(days=1):
                try:
                    api_key = os.getenv('ALPHA_VANTAGE_KEY')
                    endpoint = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={api_key}'
                    response = requests.get(endpoint)
                    data = response.json()

                    if 'Time Series (Daily)' in data:
                        daily_data = data['Time Series (Daily)']
                        recent_data = []

                        for date_str, daily_info in daily_data.items():
                            date_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
                            if date_dt > latest_date:
                                close_price = float(daily_info['4. close'])
                                recent_data.append((date_dt, close_price))

                        price_data.extend(recent_data)
                        price_data.sort(key=lambda x: x[0])

                except Exception as e:
                    print(f"Error fetching recent data from API for {ticker}: {str(e)}")

        return price_data

    except Exception as e:
        print(f"Error fetching historical prices for {ticker}: {str(e)}")
        return []


def generate_dummy_data(num_days: int = 252) -> List[Tuple[datetime, float]]:
    """Generate dummy price data for testing"""
    today = datetime.now()
    dummy_data = []
    base_price = 100.0

    for i in range(num_days):
        day = today - timedelta(days=i)
        if day.weekday() < 5:  # Only weekdays
            price_variation = random.uniform(-0.5, 0.5)
            dummy_data.append((day, base_price + price_variation))
            base_price += price_variation  # Allow for price drift

    # Sort ascending by date
    dummy_data.sort(key=lambda x: x[0])
    return dummy_data


def fetch_credit_spread_data(ticker: str) -> Dict[str, float]:
    """
    Fetch credit spread data
    """
    return {
        'spread': 100.0,  # dummy data for display
        'rating': 'BBB'
    }


def fetch_market_data() -> List[float]:
    """
    Fetch market benchmark data (S&P 500)
    """
    return [0.0001] * 252  # Dummy data - one year of daily returns
