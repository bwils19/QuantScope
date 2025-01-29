# backend/analytics/market_data.py

import requests
import numpy as np
from typing import Dict, List
import random
import os


import os
import requests
import datetime
from typing import List, Tuple


def fetch_historical_prices(ticker: str) -> List[Tuple[datetime.datetime, float]]:
    """
    Fetch historical price data from Alpha Vantage (if available),
    otherwise return dummy data in the format [(date, price), (date, price), ...].
    """
    try:
        api_key = os.getenv('ALPHA_VANTAGE_KEY')
        endpoint = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={api_key}'
        response = requests.get(endpoint)
        data = response.json()

        # Check if the API response contains the "Time Series (Daily)" key
        if 'Time Series (Daily)' not in data:
            print(f"Alpha Vantage response missing 'Time Series (Daily)' for {ticker}, using dummy data.")
            return generate_dummy_data()

        # Parse the time series data into a list of (datetime, close_price)
        daily_data = data['Time Series (Daily)']
        historical_data = []
        for date_str, daily_info in daily_data.items():
            date_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            close_price = float(daily_info['4. close'])
            historical_data.append((date_dt, close_price))

        # Sort data by ascending date
        historical_data.sort(key=lambda x: x[0])
        return historical_data

    except Exception as e:
        print(f"Error fetching historical prices for {ticker}: {str(e)}")
        # Fallback to dummy data on error
        return generate_dummy_data()


def generate_dummy_data(num_days: int = 252) -> List[Tuple[datetime.datetime, float]]:
    """
    Generate a list of (date, price) tuples for testing or fallback.
    Currently, this returns `num_days` points of 100.0 for each day (including weekends).
    """
    today = datetime.datetime.now()
    dummy_data = []
    for i in range(num_days):
        day = today - datetime.timedelta(days=i)
        if day.weekday() < 5:
            dummy_data.append((day, 100.0))

        base_price = 100.0
        price_variation = random.uniform(-0.5, 0.5)  # small daily random change
        dummy_data.append((day, base_price + price_variation))

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
