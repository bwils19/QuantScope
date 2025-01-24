# backend/analytics/market_data.py

import requests
import numpy as np
from typing import Dict, List
import os


def fetch_historical_prices(ticker: str) -> List[float]:
    """
    Fetch historical price data from Alpha Vantage - using dummy data for now before we implement
    the actual market data pull.
    """
    try:
        api_key = os.getenv('ALPHA_VANTAGE_KEY')
        endpoint = f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={ticker}&apikey={api_key}'
        response = requests.get(endpoint)
        data = response.json()

        # For now, return dummy data for testing
        return [100.0] * 252  # One year of dummy prices
    except Exception as e:
        print(f"Error fetching historical prices for {ticker}: {str(e)}")
        return [100.0] * 252  # Return dummy data on error


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
