# backend/utils/validators.py
import json
import os
from backend.models import Security
from backend import db
from backend.services.price_update_service import PriceUpdateService


def validate_ticker(ticker):
    ticker = ticker.strip().upper()

    # First check database
    security = Security.query.filter_by(ticker=ticker).first()
    if security:
        return True, security.name

    # Check symbols.json
    try:
        symbols_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                                    'static', 'data', 'symbols.json')

        if os.path.exists(symbols_path):
            with open(symbols_path, 'r') as f:
                symbols = json.load(f)

            for symbol in symbols:
                if symbol.get('symbol', '').upper() == ticker:
                    return True, symbol.get('name')

        # If not found in symbols.json, try API validation
        service = PriceUpdateService()
        # this is the function i want to grab a single ticker
        price_data = service._fetch_ticker_data(ticker)

        if price_data and 'currentPrice' in price_data:
            return True, ticker  # We don't have the name, so just return the ticker

    except Exception as e:
        print(f"Error validating ticker {ticker}: {str(e)}")

    # If all checks fail, it's not valid
    return False, None