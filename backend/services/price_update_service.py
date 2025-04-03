# backend/services/price_update_service.py
import os
import time
import traceback
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
from backend.models import StockCache, Portfolio, Security, RiskAnalysisCache, SecurityHistoricalData, PortfolioSecurity
from backend.celery_app import celery
from backend.services.stock_service import is_market_open
# from backend.tasks import logger


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

    def _create_session(self):
        """Create a direct SQLAlchemy session with connection pool management"""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        import os
        from dotenv import load_dotenv

        load_dotenv()

        database_url = os.getenv('DATABASE_URL')
        if database_url:
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://')
        else:
            # Fallback to SQLite
            import os.path
            basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
            database_url = f"sqlite:///{os.path.join(basedir, 'instance', 'users.db')}"

        # Enhanced engine with connection pool settings
        engine = create_engine(
            database_url,
            pool_size=5,  # Max connections in pool
            max_overflow=10,  # Max overflow allowed
            pool_timeout=30,  # Sec to wait for connection
            pool_recycle=1800,  # Recycle connections after 30 min
            pool_pre_ping=True  # Verify connections before use
        )

        Session = sessionmaker(bind=engine)
        return Session()

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
            session = self._create_session()
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

    def update_prices_for_portfolio(self, portfolio_id):
        """Update prices for a specific portfolio"""
        try:
            # logger.info(f"Updating prices for portfolio {portfolio_id}")

            with db.session.begin() as session:
                # Get the portfolio
                portfolio = session.query(Portfolio).get(portfolio_id)
                if not portfolio:
                    return {
                        'success': False,
                        'error': f"Portfolio {portfolio_id} not found"
                    }

                # Get all securities in this portfolio via the junction table
                portfolio_securities = session.query(PortfolioSecurity).filter_by(portfolio_id=portfolio_id).all()
                security_ids = [ps.security_id for ps in portfolio_securities]
                securities = session.query(Security).filter(Security.id.in_(security_ids)).all()

                if not securities:
                    return {
                        'success': True,
                        'message': "No securities found in portfolio",
                        'updated_count': 0
                    }

                # Extract unique tickers
                tickers = list(set([s.ticker for s in securities]))

                # Fetch prices for all tickers
                prices = self._fetch_prices(tickers)

                # Update securities with new prices
                updated_count, failed_count = self._update_securities_with_prices(session, securities, prices)

                # Update portfolio totals
                self._update_portfolio_totals_for_single_portfolio(session, portfolio)

                # Prepare the response
                return {
                    'success': True,
                    'updated_count': updated_count,
                    'failed_count': failed_count,
                    'tickers_updated': list(prices.keys()),
                    'timestamp': datetime.utcnow().isoformat(),
                    'portfolio_id': portfolio_id
                }

        except Exception as e:
            #logger.error(f"Error updating prices for portfolio {portfolio_id}: {str(e)}")
            traceback.print_exc()
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
            session = self._create_session()

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
        Returns: Dict mapping tickers to their cached data
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

    def _update_securities_with_prices(self, session, securities, prices):
        """Update securities with new prices and recalculate portfolio securities values"""
        updated_count = 0
        failed_count = 0

        for security in securities:
            try:
                # Get the price data for this ticker
                ticker = security.ticker
                if ticker not in prices:
                    continue

                price_data = prices[ticker]
                new_price = float(price_data['currentPrice'])
                prev_close = float(price_data.get('previousClose', security.current_price or new_price))

                # Update the security's current price
                old_price = security.current_price
                security.current_price = new_price
                security.previous_close = prev_close
                security.updated_at = datetime.utcnow()

                # Find all portfolio_securities entries for this security
                portfolio_securities = session.query(PortfolioSecurity).filter_by(security_id=security.id).all()

                # Update each portfolio security
                for ps in portfolio_securities:
                    # Calculate new values
                    ps.total_value = ps.amount_owned * new_price
                    ps.value_change = ps.amount_owned * (new_price - prev_close)

                    # Calculate percentage changes
                    if prev_close and prev_close > 0:
                        ps.value_change_pct = (ps.value_change / (ps.amount_owned * prev_close)) * 100

                    # Update total gain if purchase price exists
                    if ps.purchase_price:
                        ps.total_gain = ps.total_value - (ps.amount_owned * ps.purchase_price)
                        if ps.purchase_price > 0:
                            ps.total_gain_pct = ((ps.total_value / (ps.amount_owned * ps.purchase_price)) - 1) * 100

                updated_count += 1

            except Exception as e:
                failed_count += 1
                # logger.error(f"Error updating security {security.ticker}: {str(e)}")
                import traceback
                # logger.error(traceback.format_exc())

        return updated_count, failed_count

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

    def _update_portfolio_totals(self, session=None):
        """Update portfolio totals based on portfolio_securities values"""
        # logger.info("Updating portfolio totals based on new prices")

        close_session = False
        if session is None:
            session = db.session()
            close_session = True

        try:
            # logger.info("Updating totals for all portfolios")
            portfolios = session.query(Portfolio).all()
            # logger.info(f"Found {len(portfolios)} portfolios to update")

            for portfolio in portfolios:
                try:
                    # Calculate aggregates directly in the database for efficiency
                    aggregates = session.query(
                        func.sum(PortfolioSecurity.total_value).label('total_value'),
                        func.sum(PortfolioSecurity.value_change).label('day_change'),
                        func.sum(PortfolioSecurity.total_gain).label('total_gain'),
                        func.count().label('count')
                    ).filter(
                        PortfolioSecurity.portfolio_id == portfolio.id
                    ).first()

                    if aggregates:
                        # Update portfolio with aggregate values
                        portfolio.total_value = aggregates.total_value or 0
                        portfolio.day_change = aggregates.day_change or 0
                        portfolio.total_gain = aggregates.total_gain or 0
                        portfolio.total_holdings = aggregates.count

                        # Calculate percentages
                        if portfolio.total_value > 0:
                            # Day change percentage
                            base_value = portfolio.total_value - portfolio.day_change
                            if base_value > 0:
                                portfolio.day_change_pct = (portfolio.day_change / base_value) * 100

                            # Calculate cost basis for gain percentage
                            cost_basis_result = session.query(
                                func.sum(PortfolioSecurity.amount_owned * PortfolioSecurity.purchase_price)
                            ).filter(
                                PortfolioSecurity.portfolio_id == portfolio.id,
                                PortfolioSecurity.purchase_price.isnot(None)
                            ).scalar()

                            cost_basis = cost_basis_result or 0
                            if cost_basis > 0:
                                portfolio.total_gain_pct = ((portfolio.total_value / cost_basis) - 1) * 100

                    portfolio.updated_at = datetime.utcnow()

                except Exception as e:
                    print(f"Error updating portfolio {portfolio.id}: {str(e)}")
                    # logger.error(f"Error updating portfolio {portfolio.id}: {str(e)}")

            # Commit changes
            session.commit()
            # logger.info("Portfolio totals updated successfully")

        except Exception as e:
            # logger.error(f"Error updating portfolio totals: {str(e)}")
            import traceback
            # logger.error(traceback.format_exc())
            session.rollback()
        finally:
            if close_session:
                session.close()

    def _invalidate_risk_cache(self, portfolio_id: int, session=None) -> None:
        """Invalidate risk analysis cache for a portfolio."""
        try:
            # Use provided session or create a new one
            use_provided_session = session is not None
            if not use_provided_session:
                self.logger.debug(f"Creating new session for risk cache invalidation (portfolio {portfolio_id})")
                session = self._create_session()

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
            with self._create_session() as session:
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

    def _update_portfolio_totals_for_single_portfolio(self, session, portfolio):
        """Update totals for a single portfolio"""
        try:
            # Get all portfolio_securities records for this portfolio
            portfolio_securities = session.query(PortfolioSecurity).filter_by(portfolio_id=portfolio.id).all()

            total_value = 0
            day_change = 0
            total_gain = 0

            for ps in portfolio_securities:
                total_value += ps.total_value if ps.total_value else 0
                day_change += ps.value_change if ps.value_change else 0
                total_gain += ps.total_gain if ps.total_gain else 0

            # Update portfolio with new totals
            portfolio.total_value = total_value
            portfolio.day_change = day_change

            # Calculate percentages
            portfolio.day_change_pct = (day_change / (total_value - day_change)) * 100 if (
                                                                                                      total_value - day_change) > 0 else 0

            # Update total gain
            portfolio.total_gain = total_gain

            # Calculate cost basis for gain percentage
            cost_basis = sum(
                [(ps.amount_owned * ps.purchase_price) for ps in portfolio_securities if ps.purchase_price]) or 0
            if cost_basis > 0:
                portfolio.total_gain_pct = ((total_value / cost_basis) - 1) * 100

                # Calculate total return
                self.calculate_total_return(portfolio, session)
                
            # Update total holdings count
            portfolio.total_holdings = len(portfolio_securities)

            # Update timestamp
            portfolio.updated_at = datetime.utcnow()

            return True

        except Exception as e:
            # logger.error(f"Error updating portfolio {portfolio.id} totals: {str(e)}")
            traceback.print_exc()
            return False

    
    
    def update_portfolio_metrics(self, portfolio_id):
        """Update comprehensive metrics for a portfolio including day change and total return."""
        self.logger.info(f"Updating comprehensive metrics for portfolio {portfolio_id}")
        
        try:
            with db.session.begin() as session:
                # Get the portfolio
                portfolio = session.query(Portfolio).get(portfolio_id)
                if not portfolio:
                    self.logger.warning(f"Portfolio {portfolio_id} not found")
                    return {"success": False, "error": "Portfolio not found"}
                
                # Get all portfolio securities with joined security data
                portfolio_securities = (
                    session.query(PortfolioSecurity, Security)
                    .join(Security, PortfolioSecurity.security_id == Security.id)
                    .filter(PortfolioSecurity.portfolio_id == portfolio_id)
                    .all()
                )
                
                # Track totals
                total_value = 0
                total_cost_basis = 0
                day_change = 0
                total_gain = 0
                
                for ps, security in portfolio_securities:
                    # Use consistent price data
                    current_price = security.current_price or 0
                    previous_close = security.previous_close or current_price
                    
                    # Calculate security metrics
                    security_value = ps.amount_owned * current_price
                    security_day_change = ps.amount_owned * (current_price - previous_close)
                    
                    # Update portfolio_security values
                    ps.total_value = security_value
                    ps.value_change = security_day_change
                    
                    # Calculate percentage changes only if denominators are non-zero
                    prev_day_value = ps.amount_owned * previous_close
                    if prev_day_value > 0:
                        ps.value_change_pct = (security_day_change / prev_day_value) * 100
                    else:
                        ps.value_change_pct = 0
                    
                    # Calculate gain/loss using purchase price
                    if ps.purchase_price and ps.purchase_price > 0:
                        security_cost = ps.amount_owned * ps.purchase_price
                        security_gain = security_value - security_cost
                        
                        ps.total_gain = security_gain
                        ps.total_gain_pct = (security_gain / security_cost) * 100 if security_cost > 0 else 0
                        
                        # Add to portfolio totals
                        total_cost_basis += security_cost
                        total_gain += security_gain
                    else:
                        ps.total_gain = 0
                        ps.total_gain_pct = 0
                    
                    # Add to portfolio totals
                    total_value += security_value
                    day_change += security_day_change
                
                # Update portfolio totals
                portfolio.total_value = total_value
                portfolio.day_change = day_change
                
                # Calculate percentage changes for portfolio
                day_base = total_value - day_change
                if day_base > 0:
                    portfolio.day_change_pct = (day_change / day_base) * 100
                else:
                    portfolio.day_change_pct = 0
                
                portfolio.total_gain = total_gain
                if total_cost_basis > 0:
                    portfolio.total_gain_pct = (total_gain / total_cost_basis) * 100
                else:
                    portfolio.total_gain_pct = 0
                
                # Calculate total return
                self.calculate_total_return(portfolio, session)
                portfolio.updated_at = datetime.utcnow()
                
                # Commit changes
                session.commit()
                
                self.logger.info(f"Portfolio {portfolio_id} metrics updated successfully")
                self.logger.info(f"  Total value: ${total_value}")
                self.logger.info(f"  Day change: ${day_change} ({portfolio.day_change_pct:.2f}%)")
                self.logger.info(f"  Total gain: ${total_gain} ({portfolio.total_gain_pct:.2f}%)")
                self.logger.info(f"  Total return: ${portfolio.total_return} ({portfolio.total_return_pct:.2f}%)")
                
                return {
                    "success": True,
                    "portfolio_id": portfolio_id,
                    "total_value": total_value,
                    "day_change": day_change,
                    "total_gain": total_gain,
                    "total_return": portfolio.total_return
                }
        
        except Exception as e:
            self.logger.error(f"Error updating portfolio metrics: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
def calculate_total_return(self, portfolio, session=None):
        """Calculate total return for a portfolio based on purchase prices."""
        self.logger.info(f"Calculating total return for portfolio {portfolio.id}")
        
        close_session = False
        if session is None:
            session = db.session()
            close_session = True
        
        try:
            # Get current portfolio value
            current_value = portfolio.total_value
            
            # Get initial investment (sum of purchase prices * amounts)
            portfolio_securities = session.query(PortfolioSecurity).filter_by(
                portfolio_id=portfolio.id
            ).all()
            
            initial_value = sum(
                ps.purchase_price * ps.amount_owned
                for ps in portfolio_securities
                if ps.purchase_price is not None and ps.purchase_price > 0
            )
            
            self.logger.info(f"Portfolio {portfolio.id}: Current value: ${current_value}, Initial value: ${initial_value}")
            
            if initial_value > 0:
                # Calculate return
                absolute_return = current_value - initial_value
                percent_return = (current_value / initial_value - 1) * 100
                
                # Update portfolio
                portfolio.total_return = absolute_return
                portfolio.total_return_pct = percent_return
                
                self.logger.info(f"Portfolio {portfolio.id}: Total return: ${absolute_return} ({percent_return:.2f}%)")
            else:
                self.logger.warning(f"Portfolio {portfolio.id}: No valid initial value found, setting total return to 0")
                portfolio.total_return = 0
                portfolio.total_return_pct = 0
        
        except Exception as e:
            self.logger.error(f"Error calculating total return for portfolio {portfolio.id}: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
        
        finally:
            if close_session:
                session.close()

def recalculate_all_portfolio_metrics(self):
    """Recalculate metrics for all portfolios to ensure day change and total return values are set."""
    self.logger.info("Recalculating metrics for all portfolios...")
    
    try:
        # Create a new session
        session = self._create_session()
        
        try:
            # Get all portfolios
            from backend.models import Portfolio
            portfolios = session.query(Portfolio).all()
            self.logger.info(f"Found {len(portfolios)} portfolios to update")
            
            success_count = 0
            error_count = 0
            
            for portfolio in portfolios:
                try:
                    # Update portfolio metrics
                    self.update_portfolio_metrics(portfolio.id)
                    success_count += 1
                except Exception as e:
                    self.logger.error(f"Error updating portfolio {portfolio.id}: {str(e)}")
                    error_count += 1
            
            self.logger.info(f"Portfolio metrics update complete. Success: {success_count}, Errors: {error_count}")
            return {
                'success': True,
                'total': len(portfolios),
                'success_count': success_count,
                'error_count': error_count
            }
        
        finally:
            session.close()
    
    except Exception as e:
        self.logger.error(f"Error recalculating portfolio metrics: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
def get_security_overview(self, ticker):
        BASE_URL = "https://www.alphavantage.co/query"
        response = requests.get(BASE_URL, params={
            "function": "OVERVIEW",
            "symbol": ticker,
            "apikey": self.api_key
        })
        return response.json()

def get_global_quote(self, ticker):
    BASE_URL = "https://www.alphavantage.co/query"
    response = requests.get(BASE_URL, params={
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": self.api_key
    })
    return response.json()



@celery.task(name='scheduled_price_update', bind=True, max_retries=3)
def scheduled_price_update(self):
    """
    Celery task to update all portfolio prices every 5 minutes during market hours.
    """
    service = PriceUpdateService()
    service.logger.info("Running scheduled price update via Celery...")
    
    try:
        # Check if market is open
        from backend.services.stock_service import is_market_open
        if not is_market_open():
            service.logger.info("Market is closed, skipping price update.")
            return {"success": False, "message": "Market closed"}
            
        result = service.update_all_portfolio_prices()
        service.logger.info(f"Scheduled update complete: {result}")
        return result
    except Exception as e:
        service.logger.error(f"Error in scheduled price update: {str(e)}", exc_info=True)
        # Retry the task with exponential backoff
        retry_in = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
        self.retry(exc=e, countdown=retry_in)

@celery.task(name='save_closing_prices', bind=True, max_retries=3)
def save_closing_prices(self):
    """
    Celery task to save the final stock prices at the end of the market day.
    Moves the final prices from StockCache to SecurityHistoricalData.
    """
    service = PriceUpdateService()
    service.logger.info("Starting save_closing_prices task...")
    
    # Import the correct is_market_open function
    from backend.services.stock_service import is_market_open
    if is_market_open():
        service.logger.info("Market still open, skipping final price save.")
        return {"success": False, "message": "Market still open"}

    session = db.session
    try:
        service.logger.info("Saving closing prices from StockCache into SecurityHistoricalData...")
        all_cache_entries = session.query(StockCache).all()
        
        if not all_cache_entries:
            service.logger.warning("No cache entries found to save as historical data")
            return {"success": False, "message": "No cache entries found"}
            
        count = 0
        for cache_entry in all_cache_entries:
            try:
                if not cache_entry.data or "currentPrice" not in cache_entry.data:
                    service.logger.warning(f"Invalid cache data for {cache_entry.ticker}, skipping")
                    continue
                    
                # Check if we already have an entry for this date
                today = datetime.utcnow().date()
                existing = session.query(SecurityHistoricalData).filter_by(
                    ticker=cache_entry.ticker,
                    date=today
                ).first()
                
                if existing:
                    # Update existing entry
                    existing.close_price = cache_entry.data["currentPrice"]
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new entry
                    historical_entry = SecurityHistoricalData(
                        ticker=cache_entry.ticker,
                        date=today,
                        close_price=cache_entry.data["currentPrice"]
                    )
                    session.add(historical_entry)
                count += 1
            except Exception as item_error:
                service.logger.error(f"Error processing {cache_entry.ticker}: {str(item_error)}")
                continue

        session.commit()
        service.logger.info(f"Closing prices successfully saved for {count} securities.")
        return {"success": True, "count": count}

    except Exception as e:
        session.rollback()
        service.logger.error(f"Error saving closing prices: {str(e)}", exc_info=True)
        
        # Retry the task with exponential backoff
        retry_in = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
        self.retry(exc=e, countdown=retry_in)
        
        return {"success": False, "error": str(e)}

    finally:
        session.close()

@celery.task(name='update_prices', bind=True, max_retries=3)
def update_prices(self):
    """Update prices for all securities in active portfolios."""
    service = PriceUpdateService()
    result = service.update_all_portfolio_prices()
    return result

@celery.task(name='update_historical_data', bind=True, max_retries=3)
def update_historical_data(self):
    """
    Celery task to update historical data after market close.
    This task adds daily closing prices to the historical record.
    """
    service = PriceUpdateService()
    service.logger.info("Starting historical data update task...")
    
    # Import the historical data service
    from backend.services.historical_data_service import HistoricalDataService
    
    try:
        # Create historical data service
        historical_service = HistoricalDataService()
        
        # Check if we should fetch market data
        should_fetch, reason = historical_service.market_utils.should_fetch_market_data()
        
        if not should_fetch:
            service.logger.info(f"Skipping historical data update: {reason}")
            return {"success": False, "message": reason}
        
        # Run the update
        result = historical_service.update_historical_data()
        service.logger.info(f"Historical data update complete: {result}")
        return result
        
    except Exception as e:
        service.logger.error(f"Error in historical data update: {str(e)}", exc_info=True)
        
        # Retry the task with exponential backoff
        retry_in = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
        self.retry(exc=e, countdown=retry_in)
        
        return {"success": False, "error": str(e)}

