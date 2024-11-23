import matplotlib
import pandas as pd
import matplotlib.pyplot as plt
matplotlib.use('TkAgg')
import os

# Paths
RAW_DATA_PATH = "../data/raw/"
PROCESSED_DATA_PATH = "../data/processed/"


def load_data(symbol):
    """
    Load stock data from the raw directory.
    :param symbol: Stock ticker symbol.
    :return: DataFrame with stock data.
    """
    file_path = os.path.join(RAW_DATA_PATH, f"{symbol}_daily.csv")
    if os.path.exists(file_path):
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        print(f"Data loaded for {symbol}.")
        return df
    else:
        print(f"No data found for {symbol} at {file_path}.")
        return None


def plot_closing_prices(df, symbol):
    """
    Plot the closing prices of the stock.
    :param df: DataFrame containing stock data.
    :param symbol: Stock ticker symbol.
    """
    plt.figure(figsize=(10, 6))
    plt.plot(df.index, df['Close'], label="Closing Price", color='blue')
    plt.title(f"{symbol} Closing Prices")
    plt.xlabel("Date")
    plt.ylabel("Price (USD)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{PROCESSED_DATA_PATH}{symbol}_closing_prices.png")
    plt.show()


def plot_volume(df, symbol):
    """
    Plot the trading volume of the stock.
    :param df: DataFrame containing stock data.
    :param symbol: Stock ticker symbol.
    """
    plt.figure(figsize=(10, 6))
    plt.bar(df.index, df['Volume'].astype(float), label="Volume", color='orange', width=0.8)
    plt.title(f"{symbol} Trading Volume")
    plt.xlabel("Date")
    plt.ylabel("Volume")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{PROCESSED_DATA_PATH}{symbol}_volume.png")
    plt.show()


# Main execution
if __name__ == "__main__":
    symbol = "AAPL"
    os.makedirs(PROCESSED_DATA_PATH, exist_ok=True)
    data = load_data(symbol)
    if data is not None:
        plot_closing_prices(data, symbol)
        plot_volume(data, symbol)
