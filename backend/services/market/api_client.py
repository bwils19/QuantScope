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
        """Fetch daily data with rate limiting and retry logic"""
        self._handle_rate_limit()

        try:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TIME_SERIES_DAILY_ADJUSTED&"
                f"symbol={ticker}&outputsize=full&"
                f"apikey={self.api_key}"
            )

            logger.info(f"Fetching data for {ticker}")
            response = self.session.get(url, timeout=10)

            # Update rate limit tracking
            self.rate_limit_remaining -= 1

            if response.status_code == 429:  # Too Many Requests
                logger.warning("Rate limit exceeded")
                self.rate_limit_remaining = 0
                self._handle_rate_limit()
                return self.fetch_daily_data(ticker)  # Retry after waiting

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
            logger.error(f"Request failed for {ticker}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching data for {ticker}: {str(e)}")
            return None