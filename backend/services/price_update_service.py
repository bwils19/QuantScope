# backend/services/price_update_service.py
import os
import time
from datetime import datetime, timedelta
import threading
import logging
from typing import List, Dict, Any, Tuple, Optional
import concurrent.futures
import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import func
from urllib3.util.retry import Retry

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend import db
from backend.models import StockCache, Portfolio, Security, RiskAnalysisCache


class PriceUpdateService:
    """Service for updating security prices efficiently with Alpha Vantage API."""

    def __init__(self, api_key=None, rate_limit=75, batch_size=50):
        """Initialize the price update service.

        Args:
            api_key: Alpha Vantage API key (if None, will be loaded from env)
            rate_limit: Number of requests allowed per minute
            batch_size: Number of securities to process in a single database transaction
        """
        self.logger = logging.getLogger('prices')
        self.logger.info("Initializing PriceUpdateService")
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_KEY')
        if not self.api_key:
            self.logger.error("No Alpha Vantage API key found!")
        self.rate_limit = rate_limit  # Premium tier: 75 requests per minute
        self.batch_size = batch_size
        self.lock = threading.Lock()

        # Session with retry configuration
        self.session = self._create_request_session()
        self.logger.info(f"PriceUpdateService initialized with rate_limit={rate_limit}, batch_size={batch_size}")

    def _create_request_session(self) -> requests.Session:
        """Create a request session with retry configuration."""
        self.logger.debug("Creating request session with retry configuration")
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def update_all_portfolio_prices(self, is_weekend=None) -> Dict[str, Any]:
        """Update prices for all securities across all portfolios.
        Returns: Dict with update statistics
        """
        self.logger.info("=== Starting update of ALL portfolio prices ===")
        start_time = time.time()

        if is_weekend is None:
            is_weekend = datetime.now().weekday() >= 5

        if is_weekend:
            self.logger.info("Running in WEEKEND MODE - using Friday's closing prices")

        try:
            # Create a new session for this operation
            session = db.create_scoped_session()
            self.logger.debug("Created new database session")

            try:
                # Get all unique tickers across all portfolios
                all_tickers = session.query(Security.ticker).distinct().all()
                tickers = [ticker[0] for ticker in all_tickers]
                self.logger.info(f"Found {len(tickers)} unique tickers to update")

                if not tickers:
                    self.logger.warning("No tickers found in any portfolios")
                    return {
                        'success': True,
                        'updated_count': 0,
                        'elapsed_time': 0,
                        'message': 'No securities found to update'
                    }

                # Update prices in batches
                self.logger.info(f"Starting ticker price updates...")
                update_stats = self.update_prices_for_tickers(tickers, session, is_weekend=is_weekend)

                if not update_stats.get('success', False):
                    self.logger.error(f"Failed to update ticker prices: {update_stats.get('error', 'Unknown error')}")
                    return update_stats

                # Update portfolio totals
                self.logger.info("Updating portfolio totals based on new prices")
                self._update_portfolio_totals(session=session)

                # Log completion and return stats
                elapsed_time = time.time() - start_time
                update_stats['elapsed_time'] = elapsed_time
                update_stats['timestamp'] = datetime.now().isoformat()

                self.logger.info(f"=== Price update completed in {elapsed_time:.2f} seconds ===")
                self.logger.info(f"Updated {update_stats.get('updated_count', 0)} securities")
                self.logger.info(f"Failed for {update_stats.get('failed_count', 0)} securities")

                # Log the first few updated tickers for verification
                updated_tickers = update_stats.get('tickers_updated', [])
                if updated_tickers:
                    sample_tickers = updated_tickers[:5]
                    self.logger.info(f"Sample updated tickers: {', '.join(sample_tickers)}" +
                                     (f" and {len(updated_tickers) - 5} more" if len(updated_tickers) > 5 else ""))

                return update_stats

            finally:
                self.logger.debug("Closing database session")
                session.close()

        except Exception as e:
            self.logger.error(f"Error updating all portfolio prices: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    def update_prices_for_portfolio(self, portfolio_id: int) -> Dict[str, Any]:
        """Update prices for a specific portfolio.

        Args:
            portfolio_id: ID of the portfolio to update

        Returns:
            Dict with update statistics
        """
        self.logger.info(f"=== Starting price update for portfolio {portfolio_id} ===")
        start_time = time.time()

        try:
            # Get portfolio to verify it exists
            portfolio = db.session.query(Portfolio).get(portfolio_id)
            if not portfolio:
                self.logger.error(f"Portfolio {portfolio_id} not found")
                return {
                    'success': False,
                    'error': f'Portfolio {portfolio_id} not found'
                }

            self.logger.info(f"Updating prices for portfolio: {portfolio.name} (ID: {portfolio_id})")

            # Get securities for this portfolio
            securities = Security.query.filter_by(portfolio_id=portfolio_id).all()
            if not securities:
                self.logger.warning(f"No securities found in portfolio {portfolio_id}")
                return {
                    'success': True,
                    'updated_count': 0,
                    'message': 'No securities in portfolio to update'
                }

            tickers = [security.ticker for security in securities]
            self.logger.info(f"Found {len(tickers)} securities to update in this portfolio")

            # Fetch prices with retry logic
            self.logger.info(f"Fetching prices for {len(tickers)} tickers...")
            price_data = self._fetch_prices_with_retry(tickers)
            self.logger.info(f"Received price data for {len(price_data)} tickers")

            # Check for missing tickers
            missing_tickers = [ticker for ticker in tickers if ticker not in price_data]
            if missing_tickers:
                self.logger.warning(
                    f"Failed to get prices for {len(missing_tickers)} tickers: {', '.join(missing_tickers[:5])}" +
                    (f" and {len(missing_tickers) - 5} more" if len(missing_tickers) > 5 else ""))

            # Update securities with new prices
            updated_tickers = []
            for security in securities:
                if security.ticker in price_data:
                    # Log original values for comparison
                    old_price = security.current_price
                    old_total = security.total_value

                    # Update price
                    new_price = price_data[security.ticker]['currentPrice']
                    security.current_price = new_price

                    # Calculate new total value
                    security.total_value = security.amount_owned * new_price

                    # Update value change
                    if 'previousClose' in price_data[security.ticker]:
                        prev_close = price_data[security.ticker]['previousClose']
                        security.value_change = security.amount_owned * (new_price - prev_close)
                        if prev_close != 0:  # Avoid division by zero
                            security.value_change_pct = (new_price - prev_close) / prev_close * 100

                    updated_tickers.append(security.ticker)

                    # Log the update with detailed before/after values
                    self.logger.info(f"Updated {security.ticker}: ${old_price:.2f} → ${new_price:.2f}, " +
                                     f"Total: ${old_total:.2f} → ${security.total_value:.2f}")

            if updated_tickers:
                # Commit changes
                self.logger.info(f"Committing updates for {len(updated_tickers)} securities")
                db.session.commit()

                # Update portfolio totals
                self.logger.info(f"Updating totals for portfolio {portfolio_id}")
                self._update_portfolio_totals(portfolio_id=portfolio_id)

                # Invalidate risk cache
                self.logger.info(f"Invalidating risk cache for portfolio {portfolio_id}")
                self._invalidate_risk_cache(portfolio_id)
            else:
                self.logger.warning("No securities were updated, skipping commit")

            elapsed = time.time() - start_time
            self.logger.info(f"=== Portfolio update completed in {elapsed:.2f} seconds ===")

            return {
                'success': True,
                'updated_count': len(updated_tickers),
                'tickers_updated': updated_tickers,
                'elapsed_time': elapsed,
                'timestamp': datetime.utcnow().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Error updating portfolio {portfolio_id}: {str(e)}", exc_info=True)
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }

    def _fetch_prices_with_retry(self, tickers: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch prices for a list of tickers with retry logic.

        Args:
            tickers: List of tickers to fetch prices for

        Returns:
            Dict mapping tickers to price data
        """
        self.logger.info(f"Fetching prices for {len(tickers)} tickers with retry")
        results = {}
        failed_tickers = []

        # Create batches to respect rate limit
        batch_size = min(self.rate_limit, 75)  # Cap at 75 per minute

        for i in range(0, len(tickers), batch_size):
            batch = tickers[i:i + batch_size]
            self.logger.info(
                f"Processing batch {i // batch_size + 1}/{(len(tickers) + batch_size - 1) // batch_size} " +
                f"({len(batch)} tickers)")

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(self._fetch_ticker_data, ticker): ticker for ticker in batch}

                for future in concurrent.futures.as_completed(futures):
                    ticker = futures[future]
                    try:
                        data = future.result()
                        if data:
                            results[ticker] = data
                            self.logger.debug(
                                f"Successfully fetched price for {ticker}: ${data.get('currentPrice', 'N/A')}")
                        else:
                            failed_tickers.append(ticker)
                            self.logger.warning(f"Failed to fetch data for {ticker}")
                    except Exception as e:
                        failed_tickers.append(ticker)
                        self.logger.error(f"Error fetching {ticker}: {str(e)}")

            # If there are more batches, wait to respect rate limit
            if i + batch_size < len(tickers):
                self.logger.debug(f"Waiting for rate limit before next batch...")
                time.sleep(12)  # Wait 12 seconds between batches

        self.logger.info(f"Price fetch complete. Got {len(results)}/{len(tickers)} prices " +
                         f"({len(failed_tickers)} failed)")

        return results

    def update_prices_for_tickers(self, tickers: List[str], session=None, is_weekend=None) -> Dict[str, Any]:
        """Update prices for a list of tickers, respecting API rate limits."""
        if not tickers:
            self.logger.warning("No tickers provided to update_prices_for_tickers")
            return {'success': True, 'updated_count': 0, 'failed_count': 0, 'tickers_updated': []}

        # Auto-detect weekend if not specified
        if is_weekend is None:
            is_weekend = datetime.now().weekday() >= 5  # 5=Saturday, 6=Sunday

        self.logger.info(
            f"Updating prices for {len(tickers)} tickers ({'WEEKEND MODE' if is_weekend else 'REGULAR MODE'})")

        # Use provided session or create a new one
        use_provided_session = session is not None
        if not use_provided_session:
            self.logger.debug("Creating new database session")
            session = db.create_scoped_session()

        try:
            # Get cached prices first to avoid unnecessary API calls
            start_time = time.time()
            cached_tickers = self._get_cached_tickers(tickers, session)
            cache_time = time.time() - start_time
            self.logger.info(f"Found {len(cached_tickers)} tickers in cache (in {cache_time:.2f}s)")

            # Determine which tickers need to be updated
            tickers_to_update = []
            updated_data = {}

            # For weekend mode, try to get historical data first
            if is_weekend:
                self.logger.info("Weekend mode: Looking for Friday prices in historical data")
                from backend.models import SecurityHistoricalData

                # Find most recent Friday
                today = datetime.now().date()
                days_since_friday = today.weekday() - 4 if today.weekday() > 4 else 3  # Friday is 4
                last_friday = today - timedelta(days=days_since_friday)
                self.logger.info(f"Using prices from most recent trading day: {last_friday}")

                # Get historical data for all tickers on or before Friday
                for ticker in tickers:
                    try:
                        # Find the most recent historical price
                        historical_data = session.query(SecurityHistoricalData) \
                            .filter(
                            SecurityHistoricalData.ticker == ticker,
                            SecurityHistoricalData.date <= last_friday
                        ) \
                            .order_by(SecurityHistoricalData.date.desc()) \
                            .first()

                        if historical_data and historical_data.close_price > 0:
                            # Get previous day for day change calculation
                            prev_day = session.query(SecurityHistoricalData) \
                                .filter(
                                SecurityHistoricalData.ticker == ticker,
                                SecurityHistoricalData.date < historical_data.date
                            ) \
                                .order_by(SecurityHistoricalData.date.desc()) \
                                .first()

                            price = float(historical_data.close_price)
                            prev_price = float(prev_day.close_price) if prev_day and prev_day.close_price else price

                            # Create price data dictionary
                            price_data = {
                                'currentPrice': price,
                                'previousClose': prev_price,
                                'changePercent': ((price - prev_price) / prev_price * 100) if prev_price > 0 else 0,
                                'timestamp': datetime.now().isoformat(),
                                'source': 'historical',
                                'date': historical_data.date.isoformat()
                            }

                            # Update cache and data
                            self._update_stock_cache(ticker, price_data, session)
                            updated_data[ticker] = price_data
                            self.logger.debug(
                                f"Using historical price for {ticker}: ${price} from {historical_data.date}")
                        else:
                            # Need to update from API
                            tickers_to_update.append(ticker)
                    except Exception as e:
                        self.logger.error(f"Error getting historical price for {ticker}: {str(e)}")
                        tickers_to_update.append(ticker)

                self.logger.info(f"Found historical prices for {len(updated_data)}/{len(tickers)} tickers")
                self.logger.info(f"Need to update {len(tickers_to_update)} tickers from API")

            else:
                # Normal weekday mode - use cache expiry logic
                tickers_to_update = [t for t in tickers if
                                     t not in cached_tickers or self._needs_update(cached_tickers.get(t))]
                self.logger.info(f"Need to update {len(tickers_to_update)} tickers from API")

            # The rest of your existing function remains largely the same
            # Fetch data from API in batches for tickers_to_update
            # ...

            # This part should be unchanged from your original function
            failed_tickers = []

            if tickers_to_update:
                # Process in batches to respect rate limit
                for i in range(0, len(tickers_to_update), self.rate_limit):
                    batch = tickers_to_update[i:i + self.rate_limit]
                    self.logger.info(
                        f"Processing batch {i // self.rate_limit + 1}/{(len(tickers_to_update) + self.rate_limit - 1) // self.rate_limit} " +
                        f"({len(batch)} tickers)")

                    # Use multiple threads to fetch data faster, but stay within rate limit
                    start_batch_time = time.time()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=self.rate_limit) as executor:
                        futures = {executor.submit(self._fetch_ticker_data, ticker): ticker for ticker in batch}

                        for future in concurrent.futures.as_completed(futures):
                            ticker = futures[future]
                            try:
                                result = future.result()
                                if result:
                                    updated_data[ticker] = result
                                    self.logger.debug(f"Got price for {ticker}: ${result.get('currentPrice', 'N/A')}")
                                else:
                                    failed_tickers.append(ticker)
                                    self.logger.warning(f"No valid price data returned for {ticker}")
                            except Exception as e:
                                self.logger.error(f"Error updating {ticker}: {str(e)}")
                                failed_tickers.append(ticker)

                    batch_time = time.time() - start_batch_time
                    self.logger.info(
                        f"Batch completed in {batch_time:.2f}s. Success: {len(batch) - len(failed_tickers)}, Failed: {len(failed_tickers)}")

                    # Wait to respect rate limit if there are more batches
                    if i + self.rate_limit < len(tickers_to_update):
                        self.logger.info("Waiting for rate limit before next batch...")
                        time.sleep(60)  # Wait a minute before the next batch
            else:
                self.logger.info("All prices are up to date in cache, no API calls needed")

            # For any failed tickers, try to use cached data
            for ticker in failed_tickers[:]:
                if ticker in cached_tickers:
                    self.logger.info(f"Using cached data for failed ticker {ticker}")
                    updated_data[ticker] = cached_tickers[ticker]
                    failed_tickers.remove(ticker)

            # Merge with cached data
            all_price_data = {**cached_tickers, **updated_data}
            self.logger.info(f"Total price data available: {len(all_price_data)}/{len(tickers)} tickers")

            # Update securities with the new prices
            self.logger.info("Updating securities with price data...")
            update_start = time.time()
            update_stats = self._update_securities_with_prices(all_price_data, session)
            update_time = time.time() - update_start

            update_stats['failed_count'] = len(failed_tickers)
            update_stats['failed_tickers'] = failed_tickers

            self.logger.info(f"Securities updated in {update_time:.2f}s. " +
                             f"Updated {update_stats.get('updated_count', 0)} securities " +
                             f"for {len(update_stats.get('tickers_updated', []))} tickers")

            # Don't commit if using an external session
            if not use_provided_session:
                self.logger.info("Committing changes...")
                session.commit()
                self.logger.info("Changes committed")

            return update_stats

        except Exception as e:
            self.logger.error(f"Error in price update: {str(e)}", exc_info=True)
            if not use_provided_session:
                self.logger.warning("Rolling back session due to error")
                session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if not use_provided_session:
                self.logger.debug("Closing database session")
                session.close()

    def _fetch_ticker_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest quote data for a ticker from Alpha Vantage.

        Args:
            ticker: The stock ticker symbol

        Returns:
            Dict with price data or None if failed
        """
        try:
            self.logger.debug(f"Fetching data for {ticker}")
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={self.api_key}"
            response = self.session.get(url, timeout=10)

            if not response.ok:
                self.logger.warning(f"Bad response for {ticker}: {response.status_code}")
                return None

            data = response.json()

            # Log response structure for debugging if needed
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Response data for {ticker}: {data}")

            if 'Global Quote' not in data or not data['Global Quote']:
                self.logger.warning(f"Invalid data format for {ticker}: {data}")
                return None

            quote = data['Global Quote']

            if '05. price' not in quote or not quote['05. price']:
                self.logger.warning(f"Missing price for {ticker}")
                return None

            # Get and calculate price metrics
            current_price = float(quote['05. price'])
            previous_close = float(quote['08. previous close']) if '08. previous close' in quote else current_price
            change_percent = float(quote['10. change percent'].strip('%')) if '10. change percent' in quote else 0

            self.logger.info(
                f"Fetched price for {ticker}: ${current_price} (prev: ${previous_close}, change: {change_percent}%)")

            return {
                'currentPrice': current_price,
                'previousClose': previous_close,
                'changePercent': change_percent,
                'timestamp': datetime.now().isoformat()
            }

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error for {ticker}: {str(e)}")
            return None
        except (ValueError, KeyError) as e:
            self.logger.error(f"Data processing error for {ticker}: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error fetching data for {ticker}: {str(e)}", exc_info=True)
            return None

    def _get_cached_tickers(self, tickers: List[str], session) -> Dict[str, Dict[str, Any]]:
        """Get cached price data for tickers from database.

        Args:
            tickers: List of tickers to check
            session: Database session to use

        Returns:
            Dict mapping tickers to their cached data
        """
        try:
            self.logger.debug(f"Getting cached data for {len(tickers)} tickers")
            cached_stocks = session.query(StockCache).filter(StockCache.ticker.in_(tickers)).all()
            self.logger.debug(f"Found {len(cached_stocks)} cached records")

            # Filter out records with None or invalid data
            valid_cached = {stock.ticker: stock.data for stock in cached_stocks if
                            stock.data and 'currentPrice' in stock.data}

            if len(valid_cached) < len(cached_stocks):
                self.logger.warning(f"Found {len(cached_stocks) - len(valid_cached)} cached records with invalid data")

            return valid_cached

        except Exception as e:
            self.logger.error(f"Error getting cached tickers: {str(e)}", exc_info=True)
            return {}

    def _needs_update(self, cache_data: Optional[Dict[str, Any]]) -> bool:
        """Determine if cache data needs to be updated."""
        if not cache_data:
            return True

        # Check for required fields
        if 'currentPrice' not in cache_data:
            self.logger.debug("Cache needs update: missing currentPrice")
            return True

        # Check cache age
        cache_time = cache_data.get('timestamp')
        if not cache_time:
            self.logger.debug("Cache needs update: missing timestamp")
            return True

        # Convert string timestamp to datetime object
        try:
            cache_datetime = datetime.fromisoformat(cache_time)
            now = datetime.now()
            age = now - cache_datetime

            # Check if it's a weekend
            is_weekend = now.weekday() >= 5  # 5=Saturday, 6=Sunday

            if is_weekend:
                # On weekends, I want Friday's closing prices
                # Only update if cache is from before Friday or older than 24 hours
                cache_day = cache_datetime.weekday()

                if cache_day < 4:  # Earlier than Friday
                    self.logger.debug(
                        f"Cache needs update: weekend but cache from {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][cache_day]}")
                    return True
                elif age > timedelta(hours=24):
                    self.logger.debug(
                        f"Cache needs update: weekend but cache is {age.total_seconds() / 3600:.1f} hours old")
                    return True

                self.logger.debug(
                    f"Cache is valid for weekend: from {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][cache_day]}, {age.total_seconds() / 3600:.1f} hours old")
                return False
            else:
                # During market hours, use existing 10-minute window
                if age > timedelta(minutes=10):
                    self.logger.debug(f"Cache needs update: age is {age.total_seconds() / 60:.1f} minutes")
                    return True

                self.logger.debug(f"Cache is fresh: age is {age.total_seconds() / 60:.1f} minutes")
                return False

        except (ValueError, TypeError) as e:
            self.logger.debug(f"Cache needs update: invalid timestamp format ({str(e)})")
            return True

    def _update_stock_cache(self, ticker: str, data: Dict[str, Any], session) -> None:
        """Update the stock cache in the database.
        Args:
            ticker: Ticker symbol
            data: Price data to store
            session: Database session to use
        """
        try:
            # Add timestamp to data if not present
            if 'timestamp' not in data:
                data['timestamp'] = datetime.now().isoformat()

            # Find existing cache or create new one
            cache = session.query(StockCache).filter_by(ticker=ticker).first()

            if cache:
                self.logger.debug(f"Updating existing cache for {ticker}")
                cache.date = datetime.now().date()
                cache.data = data
            else:
                self.logger.debug(f"Creating new cache for {ticker}")
                cache = StockCache(
                    ticker=ticker,
                    date=datetime.now().date(),
                    data=data
                )
                session.add(cache)

        except SQLAlchemyError as e:
            self.logger.error(f"Database error updating cache for {ticker}: {str(e)}", exc_info=True)
            raise

    def _update_securities_with_prices(self, price_data: Dict[str, Dict[str, Any]], session) -> Dict[str, Any]:
        """Update all securities with new price data.
        Args:
            price_data: Dict mapping tickers to price data
            session: Database session to use
        Returns:
            Dict with update statistics
        """
        updated_count = 0
        updated_tickers = []

        try:
            # Process in batches to avoid large transactions
            tickers = list(price_data.keys())
            self.logger.info(f"Updating {len(tickers)} tickers in securities table")

            for i in range(0, len(tickers), self.batch_size):
                batch_tickers = tickers[i:i + self.batch_size]
                self.logger.info(
                    f"Processing securities batch {i // self.batch_size + 1}/{(len(tickers) + self.batch_size - 1) // self.batch_size}")

                # Update securities in this batch
                securities = session.query(Security).filter(Security.ticker.in_(batch_tickers)).all()
                self.logger.info(f"Found {len(securities)} securities for this batch of {len(batch_tickers)} tickers")

                batch_updated = 0
                for security in securities:
                    ticker_data = price_data.get(security.ticker)
                    if not ticker_data:
                        self.logger.warning(f"No price data for {security.ticker}")
                        continue

                    # Update security with new price data
                    try:
                        # Log before values
                        old_price = security.current_price
                        old_value = security.total_value

                        # Update prices
                        self._update_security_prices(security, ticker_data)
                        updated_count += 1
                        batch_updated += 1

                        if security.ticker not in updated_tickers:
                            updated_tickers.append(security.ticker)

                        # Update cache for this ticker
                        self._update_stock_cache(security.ticker, ticker_data, session)

                        # Log the price change
                        self.logger.debug(f"Updated {security.ticker}: ${old_price} → ${security.current_price}, " +
                                          f"Value: ${old_value} → ${security.total_value}")

                    except Exception as e:
                        self.logger.error(f"Error updating security {security.ticker}: {str(e)}", exc_info=True)

                self.logger.info(f"Updated {batch_updated} securities in this batch")

                # Commit each batch separately
                if i + self.batch_size < len(tickers):
                    try:
                        session.flush()
                        self.logger.debug(f"Flushed batch {i // self.batch_size + 1}")
                    except Exception as e:
                        self.logger.error(f"Error flushing batch: {str(e)}", exc_info=True)
                        raise

            self.logger.info(f"Updated {updated_count} securities for {len(updated_tickers)} unique tickers")

            return {
                'success': True,
                'updated_count': updated_count,
                'tickers_updated': updated_tickers
            }

        except Exception as e:
            self.logger.error(f"Error in securities update: {str(e)}", exc_info=True)
            raise

    def _update_security_prices(self, security: Security, price_data: Dict[str, Any]) -> None:
        """Update a security's price and related metrics."""
        if not price_data:
            self.logger.warning(f"No price data provided for {security.ticker}")
            return

        # Get values with safety checks
        try:
            current_price = float(price_data.get('currentPrice', 0))
            prev_close = float(price_data.get('previousClose', current_price))

            # Special handling for zero or negative prices
            if current_price <= 0:
                self.logger.warning(f"Zero/negative price for {security.ticker}: {current_price}")

                # Try to get historical price
                from backend.models import SecurityHistoricalData

                # Find the most recent historical price
                historical_data = db.session.query(SecurityHistoricalData) \
                    .filter(SecurityHistoricalData.ticker == security.ticker) \
                    .order_by(SecurityHistoricalData.date.desc()) \
                    .first()

                if historical_data and historical_data.close_price > 0:
                    self.logger.info(f"Using historical price for {security.ticker}: ${historical_data.close_price}")
                    current_price = float(historical_data.close_price)
                    prev_close = current_price  # No day change when using historical data
                elif security.purchase_price and security.purchase_price > 0:
                    # Fallback to purchase price
                    self.logger.info(f"Using purchase price for {security.ticker}: ${security.purchase_price}")
                    current_price = security.purchase_price
                    prev_close = current_price  # No day change when using purchase price
                else:
                    self.logger.error(f"Could not find valid price for {security.ticker}")
                    return  # Skip update if no valid price found

            # Store original values for comparison
            old_price = security.current_price
            old_value = security.total_value or 0

            # Update price and value
            security.current_price = current_price
            security.total_value = security.amount_owned * current_price

            # Calculate day change
            security.value_change = security.amount_owned * (current_price - prev_close)

            # Calculate percent changes safely
            if prev_close != 0:
                value_change_base = security.amount_owned * prev_close
                security.value_change_pct = (
                                                        security.value_change / value_change_base) * 100 if value_change_base != 0 else 0
            else:
                security.value_change_pct = 0

            # Calculate total gain if purchase price exists
            if security.purchase_price and security.purchase_price > 0:
                security.total_gain = security.total_value - (security.amount_owned * security.purchase_price)
                security.total_gain_pct = ((security.total_value / (
                            security.amount_owned * security.purchase_price)) - 1) * 100
            else:
                security.total_gain = 0
                security.total_gain_pct = 0

            # Log the price update detail
            self.logger.debug(
                f"Security {security.ticker} updated: Price ${old_price or 0:.2f} → ${current_price:.2f}, " +
                f"Total ${old_value:.2f} → ${security.total_value:.2f}, " +
                f"Day change: ${security.value_change:.2f} ({security.value_change_pct:.2f}%)"
            )

        except (ValueError, TypeError) as e:
            self.logger.error(f"Data type error updating {security.ticker}: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error updating {security.ticker}: {str(e)}", exc_info=True)

    def _update_portfolio_totals(self, portfolio_id: Optional[int] = None, session=None) -> None:
        """Update aggregated metrics for portfolios.

        Args:
            portfolio_id: If provided, update only this portfolio
            session: Database session to use
        """
        try:
            # Use provided session or create a new one
            use_provided_session = session is not None
            if not use_provided_session:
                self.logger.debug("Creating new session for portfolio totals update")
                session = db.create_scoped_session()

            try:
                # Query portfolios to update
                if portfolio_id:
                    self.logger.info(f"Updating totals for portfolio {portfolio_id}")
                    portfolios = [session.query(Portfolio).get(portfolio_id)]
                    if not portfolios[0]:
                        self.logger.warning(f"Portfolio {portfolio_id} not found")
                        return
                else:
                    self.logger.info(f"Updating totals for all portfolios")
                    portfolios = session.query(Portfolio).all()

                self.logger.info(f"Found {len(portfolios)} portfolios to update")

                for portfolio in portfolios:
                    securities = session.query(Security).filter_by(portfolio_id=portfolio.id).all()

                    if not securities:
                        self.logger.info(f"No securities in portfolio {portfolio.id}, skipping totals update")
                        continue

                    # Log existing values for comparison
                    old_value = portfolio.total_value
                    old_change = portfolio.day_change

                    # Calculate aggregated metrics
                    portfolio.total_value = sum(s.total_value or 0 for s in securities)
                    portfolio.day_change = sum(s.value_change or 0 for s in securities)
                    portfolio.total_holdings = len(securities)

                    # Safely calculate percentage
                    base_value = portfolio.total_value - portfolio.day_change
                    if base_value and base_value != 0:
                        portfolio.day_change_pct = (portfolio.day_change / base_value) * 100
                    else:
                        portfolio.day_change_pct = 0

                    # Calculate total gain
                    total_cost = sum((s.amount_owned or 0) * (s.purchase_price or 0) for s in securities)
                    portfolio.total_gain = portfolio.total_value - total_cost
                    portfolio.total_gain_pct = ((portfolio.total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

                    # Update the last updated timestamp
                    portfolio.updated_at = datetime.utcnow()

                    self.logger.info(
                        f"Updated portfolio {portfolio.id} ('{portfolio.name}'): " +
                        f"Value ${old_value or 0:.2f} → ${portfolio.total_value:.2f}, " +
                        f"Day change ${old_change or 0:.2f} → ${portfolio.day_change:.2f} ({portfolio.day_change_pct:.2f}%), " +
                        f"Holdings: {portfolio.total_holdings}"
                    )

                    # Invalidate risk cache for this portfolio
                    self._invalidate_risk_cache(portfolio.id, session)

                    # Only commit if we created our own session
                if not use_provided_session:
                    self.logger.debug("Committing portfolio total updates")
                    session.commit()
                    self.logger.info("Portfolio total updates committed")

            except Exception as e:
                self.logger.error(f"Error updating portfolio totals: {str(e)}", exc_info=True)
                if not use_provided_session:
                    self.logger.warning("Rolling back session due to error")
                    session.rollback()
                raise e

            finally:
                if not use_provided_session:
                    self.logger.debug("Closing database session")
                    session.close()

        except Exception as e:
            self.logger.error(f"Failed to update portfolio totals: {str(e)}", exc_info=True)

    def _invalidate_risk_cache(self, portfolio_id: int, session=None) -> None:
        """Invalidate risk analysis cache for a portfolio."""
        try:
            # Use provided session or create a new one
            use_provided_session = session is not None
            if not use_provided_session:
                self.logger.debug(f"Creating new session for risk cache invalidation (portfolio {portfolio_id})")
                session = db.create_scoped_session()

            try:
                cache = session.query(RiskAnalysisCache).filter_by(portfolio_id=portfolio_id).first()
                if cache:
                    self.logger.info(f"Invalidating risk cache for portfolio {portfolio_id}")
                    session.delete(cache)
                else:
                    self.logger.debug(f"No risk cache found for portfolio {portfolio_id}")

                # Only commit if we created our own session
                if not use_provided_session:
                    self.logger.debug("Committing risk cache invalidation")
                    session.commit()

            except Exception as e:
                self.logger.error(f"Error invalidating risk cache: {str(e)}", exc_info=True)
                if not use_provided_session:
                    session.rollback()
                raise e

            finally:
                if not use_provided_session:
                    session.close()

        except Exception as e:
            self.logger.error(f"Failed to invalidate risk cache: {str(e)}", exc_info=True)

    def _get_historical_price(self, ticker: str) -> Optional[float]:
        """Get the most recent valid historical price for a ticker."""
        try:
            today = datetime.now().date()

            # For weekends, look for Friday's data
            if today.weekday() >= 5:  # Saturday or Sunday
                # Calculate the most recent Friday
                days_to_subtract = today.weekday() - 4  # 5-4=1 for Saturday, 6-4=2 for Sunday
                target_date = today - timedelta(days=days_to_subtract)
            else:
                # For weekdays, just use yesterday
                target_date = today - timedelta(days=1)

            from backend.models import SecurityHistoricalData

            # Query for the most recent data on or before the target date
            with db.create_scoped_session() as session:
                historical_data = session.query(
                    SecurityHistoricalData
                ).filter(
                    SecurityHistoricalData.ticker == ticker,
                    SecurityHistoricalData.date <= target_date
                ).order_by(
                    SecurityHistoricalData.date.desc()
                ).first()

                if historical_data and historical_data.close_price:
                    return float(historical_data.close_price)

            return None

        except Exception as e:
            self.logger.error(f"Error getting historical price for {ticker}: {str(e)}")
            return None