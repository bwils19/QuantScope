import time
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import logging

logger = logging.getLogger(__name__)


class AlphaVantageClient:
    def __init__(self, api_key, max_retries=3, backoff_factor=1.0):
        self.api_key = api_key
        self.session = self._create_session(max_retries, backoff_factor)
        self.rate_limit_remaining = 50
        self.rate_limit_reset = datetime.now()
        self.base_url = "https://www.alphavantage.co/query"

    def _create_session(self, max_retries, backoff_factor):
        """Create a session with retry logic"""
        session = requests.Session()

        retries = Retry(
            total=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )

        adapter = HTTPAdapter(max_retries=retries)
        session.mount('https://', adapter)
        return session

    def _handle_rate_limit(self):
        """Handle API rate limiting"""
        now = datetime.now()
        if now < self.rate_limit_reset:
            sleep_time = (self.rate_limit_reset - now).total_seconds()
            logger.info(f"Rate limit reached. Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)

        if self.rate_limit_remaining <= 0:
            self.rate_limit_reset = datetime.now() + timedelta(minutes=1)
            self.rate_limit_remaining = 5
            sleep_time = 60  # Wait for a full minute
            logger.info(f"Rate limit reset. Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)

def fetch_daily_data(self, ticker):
    retries = 0
    while retries < 5:
        self._handle_rate_limit()
        try:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TIME_SERIES_DAILY_ADJUSTED&"
                f"symbol={ticker}&outputsize=full&"
                f"apikey={self.api_key}"
            )

            logger.info(f"Fetching data for {ticker} (attempt {retries+1})")
            response = self.session.get(url, timeout=10)
            logger.info(f"Response status code for {ticker}: {response.status_code}")

            self.rate_limit_remaining -= 1

            if response.status_code == 429:
                logger.warning(f"Rate limit hit for {ticker}, backing off")
                self.rate_limit_remaining = 0
                retries += 1
                continue

            response.raise_for_status()
            data = response.json()

            if 'Error Message' in data:
                logger.error(f"API error for {ticker}: {data['Error Message']}")
                return None

            if 'Time Series (Daily)' not in data:
                logger.error(f"No daily time series data found for {ticker}")
                return None

            return data['Time Series (Daily)']

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {ticker}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching data for {ticker}: {e}")

        retries += 1
        time.sleep(2 ** retries)  # exponential backoff

    logger.error(f"Failed to fetch data for {ticker} after {retries} retries")
    return None

    def fetch_security_overview(self, ticker):
        """Fetch company overview data including sector, industry, etc."""
        try:
            params = {
                "function": "OVERVIEW",
                "symbol": ticker,
                "apikey": self.api_key
            }

            response = requests.get(self.base_url, params=params)
            if response.status_code != 200:
                logger.error(f"Failed to fetch overview for {ticker}: {response.status_code}")
                return None

            data = response.json()

            # Check for error messages
            if "Error Message" in data:
                logger.error(f"API error for {ticker}: {data['Error Message']}")
                return None

            return {
                'ticker': ticker,
                'sector': data.get('Sector'),
                'industry': data.get('Industry'),
                'asset_type': self._determine_asset_type(data),
                'currency': data.get('Currency', 'USD'),  # Default to USD if not specified
                'exchange': data.get('Exchange'),
                'last_updated': datetime.utcnow()
            }

        except Exception as e:
            logger.error(f"Error fetching overview for {ticker}: {str(e)}")
            return None

    def _determine_asset_type(self, overview_data):
        """Determine asset type based on overview data"""
        exchange = overview_data.get('Exchange', '').upper()
        asset_type = 'Stock'  # Default

        if 'ETF' in overview_data.get('AssetType', '').upper():
            asset_type = 'ETF'
        elif exchange in ['NYSE', 'NASDAQ']:
            asset_type = 'Stock'
        elif exchange in ['FOREX']:
            asset_type = 'Currency'

        return asset_type
