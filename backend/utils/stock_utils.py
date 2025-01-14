# backend/utils/stock_utils.py
import httpx
from datetime import datetime
from backend.models import StockCache
from backend import db


async def fetch_stock_data(symbol, api_key):
    try:
        async with httpx.AsyncClient() as client:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={symbol}&apikey={api_key}"
            response = await client.get(url)
            data = response.json()

            if 'Global Quote' in data:
                quote = data['Global Quote']
                stock_info = {
                    'currentPrice': float(quote['05. price']),
                    'previousClose': float(quote['08. previous close']),
                    'changePercent': float(quote['10. change percent'].rstrip('%'))
                }
                return stock_info
        return None
    except Exception as e:
        print(f"Error fetching stock data: {e}")
        return None