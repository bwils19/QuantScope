from flask import Blueprint, request, jsonify
import requests
import os
from dotenv import load_dotenv

load_dotenv()
print("Environment variables loaded")  # Debugging

stock_blueprint = Blueprint('stocks', __name__)

ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_KEY')
# print("Alpha Vantage API Key:", ALPHA_VANTAGE_API_KEY)


@stock_blueprint.route('/stocks', methods=['POST'])
def fetch_stock_data():
    print("Received request on /stocks")  # Debugging
    data = request.json
    print("Request data:", data)  # Debugging

    symbol = data.get('symbol')
    if not symbol:
        return jsonify({"message": "Stock symbol is required"}), 400

    # Fetch stock data from Alpha Vantage
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
    response = requests.get(url)
    print(f"Alpha Vantage response for {symbol}: {response.status_code}")  # Debugging

    stock_data = response.json()
    if "Time Series (Daily)" not in stock_data:
        return jsonify({"message": "Invalid symbol or API error"}), 400

    # Parse data for the last 30 days
    time_series = stock_data["Time Series (Daily)"]
    dates = list(time_series.keys())[:30]
    prices = [float(time_series[date]["4. close"]) for date in dates]

    print(f"Parsed data for {symbol}: dates={dates}, prices={prices}")  # Debugging

    return jsonify({
        "symbol": symbol,
        "dates": dates[::-1],  # Reverse for chronological order
        "prices": prices[::-1]
    }), 200


@stock_blueprint.route('/stocks/suggestions', methods=['GET'])
def stock_suggestions():
    query = request.args.get('query')
    if not query:
        return jsonify([])  # Return an empty list if no query is provided

    # API call to search by keywords (both ticker and company name)
    url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={query}&apikey={ALPHA_VANTAGE_API_KEY}"
    response = requests.get(url)
    data = response.json()

    if "bestMatches" not in data:
        return jsonify([])  # Return an empty list if API fails or no results

    # Extract relevant information from the API response
    suggestions = [
        {
            "symbol": match["1. symbol"],
            "name": match["2. name"]
        }
        for match in data["bestMatches"]
    ]
    return jsonify(suggestions)

