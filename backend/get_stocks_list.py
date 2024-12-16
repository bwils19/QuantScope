import requests
import csv
import json

from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

API_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_KEY')


def fetch_listing_status():
    """Fetch listing status from Alpha Vantage and save it as a JSON file."""
    params = {
        "function": "LISTING_STATUS",
        "apikey": ALPHA_VANTAGE_API_KEY,
        "state": "active"  # Fetch only active listings
    }

    response = requests.get(API_URL, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code} - {response.text}")
        return

    csv_data = response.text

    # Parse the CSV data
    csv_reader = csv.DictReader(csv_data.splitlines())
    symbols = []

    for row in csv_reader:
        symbols.append({
            "symbol": row["symbol"],
            "name": row["name"],
            "exchange": row["exchange"],
            "assetType": row["assetType"]
        })

    # Save to JSON
    output_file = "static/data/symbols.json"
    with open(output_file, "w") as json_file:
        json.dump(symbols, json_file, indent=4)

    print(f"Symbol data saved to {output_file}")


if __name__ == "__main__":
    fetch_listing_status()
