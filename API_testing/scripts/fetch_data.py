import os
import requests
import pandas as pd
from dotenv import load_dotenv
import yaml
import logging

# Load environment variables from .env file
load_dotenv()


# Configure logging
logging.basicConfig(
    filename="./logs/api_testing.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# Load config.yaml
with open("configs/config.yaml", "r") as config_file:
    config = yaml.safe_load(config_file)

# using AlphaVantage for testing purposes
API_KEY = os.getenv("ALPHA_VANTAGE_KEY")
BASE_URL = config["api"]["base_url"]
DEFAULT_SYMBOL = config["api"]["default_symbol"]
RAW_DATA_PATH = config["data"]["raw_path"]


# Function to fetch stock data
def fetch_stock_data(symbol=DEFAULT_SYMBOL, output_size="compact"):
    """
    Fetch daily stock data from Alpha Vantage API.
    :param symbol: Stock ticker symbol (e.g., 'AAPL') - just using apple for testing .
    :param output_size: 'compact' for recent data or 'full' for historical data.
    :return: DataFrame with stock data.
    """
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": API_KEY,
        "outputsize": output_size,
    }
    response = requests.get(BASE_URL, params=params)
    data = response.json()

    if "Time Series (Daily)" in data:
        # Convert JSON to DataFrame
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.columns = ["Open", "High", "Low", "Close", "Volume"]
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        return df
    else:
        logging.info("Fetching stock data...")
        if stock_data is not None:
            save_data(stock_data, DEFAULT_SYMBOL)
            logging.info(f"Data for {DEFAULT_SYMBOL} fetched and saved successfully.")
        else:
            logging.error("Failed to fetch stock data.")
        return None


# save data to CSV
def save_data(df, symbol):
    """
    Save stock data to a CSV file.
    :param df: DataFrame to save.
    :param symbol: Stock ticker symbol.
    """
    os.makedirs(RAW_DATA_PATH, exist_ok=True)
    file_path = os.path.join(RAW_DATA_PATH, f"{symbol}_daily.csv")
    df.to_csv(file_path)
    logging.info("Fetching stock data...")
    if stock_data is not None:
        save_data(stock_data, DEFAULT_SYMBOL)
        logging.info(f"Data for {DEFAULT_SYMBOL} fetched and saved successfully.")
    else:
        logging.error("Failed to fetch stock data.")


# Main execution
if __name__ == "__main__":
    print("Fetching stock data...")
    stock_data = fetch_stock_data()
    if stock_data is not None:
        save_data(stock_data, DEFAULT_SYMBOL)
