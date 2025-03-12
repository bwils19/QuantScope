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
from urllib3.util.retry import Retry

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend import db
from backend.models import StockCache, Portfolio, Security, RiskAnalysisCache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PriceUpdateService:
    """Service for updating security prices efficiently with Alpha Vantage API."""

    def __init__(self, api_key=None, rate_limit=75, batch_size=50):
        """Initialize the price update service.

        Args:
            api_key: Alpha Vantage API key (if None, will be loaded from env)
            rate_limit: Number of requests allowed per minute
            batch_size: Number of securities to process in a single database transaction
        """
        self.api_key = api_key or os.getenv('ALPHA_VANTAGE_KEY')
        self.rate_limit = rate_limit  # Premium tier: 75 requests per minute
        self.batch_size = batch_size
        self.lock = threading.Lock()

        # Session with retry configuration
        self.session = self._create_request_session()

    def _create_request_session(self) -> requests.Session:
        """Create a request session with retry configuration."""
        session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def update_all_portfolio_prices(self) -> Dict[str, Any]:
        """Update prices for all securities across all portfolios.

        Returns:
            Dict with update statistics
        """
        logger.info("Starting price update for all portfolios")
        start_time = time.time()

        try:
            # Create a new session for this operation
            session = db.create_scoped_session()

            try:
                # Get all unique tickers across all portfolios
                all_tickers = session.query(Security.ticker).distinct().all()
                tickers = [ticker[0] for ticker in all_tickers]
                logger.info(f"Found {len(tickers)} unique tickers to update")

                # Update prices in batches
                update_stats = self.update_prices_for_tickers(tickers, session)

                # Update portfolio totals
                self._update_portfolio_totals(session=session)

                # Log completion and return stats
                elapsed_time = time.time() - start_time
                update_stats['elapsed_time'] = elapsed_time
                update_stats['timestamp'] = datetime.now().isoformat()
                logger.info(f"Completed price update in {elapsed_time:.2f} seconds")

                return update_stats

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error updating prices: {str(e)}")
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
        logger.info(f"Starting price update for portfolio {portfolio_id}")
        try:
            # Create a new session for this operation
            session = db.create_scoped_session()

            try:
                # Get all tickers in this portfolio
                securities = session.query(Security).filter_by(portfolio_id=portfolio_id).all()
                tickers = [security.ticker for security in securities]

                logger.info(f"Found {len(tickers)} securities in portfolio {portfolio_id}")

                # Update prices for these tickers
                update_stats = self.update_prices_for_tickers(tickers, session)

                # Update portfolio totals for this specific portfolio
                self._update_portfolio_totals(portfolio_id, session)

                # Invalidate risk cache
                self._invalidate_risk_cache(portfolio_id, session)

                update_stats['timestamp'] = datetime.now().isoformat()
                return update_stats

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error updating prices for portfolio {portfolio_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def update_prices_for_tickers(self, tickers: List[str], session=None) -> Dict[str, Any]:
        """Update prices for a list of tickers, respecting API rate limits.

        Args:
            tickers: List of tickers to update
            session: Optional database session to use

        Returns:
            Dict with update statistics
        """
        if not tickers:
            return {'success': True, 'updated_count': 0, 'failed_count': 0, 'tickers_updated': []}

        logger.info(f"Updating prices for {len(tickers)} tickers")

        # Use provided session or create a new one
        use_provided_session = session is not None
        if not use_provided_session:
            session = db.create_scoped_session()

        try:
            # Get cached prices first to avoid unnecessary API calls
            cached_tickers = self._get_cached_tickers(tickers, session)
            logger.info(f"Found {len(cached_tickers)} tickers in cache")

            # Determine which tickers need to be updated
            tickers_to_update = [t for t in tickers if
                                 t not in cached_tickers or self._needs_update(cached_tickers.get(t))]
            logger.info(f"Need to update {len(tickers_to_update)} tickers from API")

            # Update tickers in batches within rate limit
            updated_data = {}
            failed_tickers = []

            # Process in batches to respect rate limit
            for i in range(0, len(tickers_to_update), self.rate_limit):
                batch = tickers_to_update[i:i + self.rate_limit]
                logger.info(f"Processing batch of {len(batch)} tickers")

                # Use multiple threads to fetch data faster, but stay within rate limit
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.rate_limit) as executor:
                    futures = {executor.submit(self._fetch_ticker_data, ticker): ticker for ticker in batch}

                    for future in concurrent.futures.as_completed(futures):
                        ticker = futures[future]
                        try:
                            result = future.result()
                            if result:
                                updated_data[ticker] = result
                            else:
                                failed_tickers.append(ticker)
                        except Exception as e:
                            logger.error(f"Error updating {ticker}: {str(e)}")
                            failed_tickers.append(ticker)

                # Wait to respect rate limit if there are more batches
                if i + self.rate_limit < len(tickers_to_update):
                    logger.info("Waiting for rate limit...")
                    time.sleep(60)  # Wait a minute before the next batch

            # Merge with cached data
            all_price_data = {**cached_tickers, **updated_data}

            # Update securities with the new prices
            update_stats = self._update_securities_with_prices(all_price_data, session)
            update_stats['failed_count'] = len(failed_tickers)
            update_stats['failed_tickers'] = failed_tickers

            # Don't commit if using an external session
            if not use_provided_session:
                session.commit()

            return update_stats

        except Exception as e:
            logger.error(f"Error in price update: {str(e)}")
            if not use_provided_session:
                session.rollback()
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            if not use_provided_session:
                session.close()

    def _fetch_ticker_data(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Fetch the latest quote data for a ticker from Alpha Vantage.

        Args:
            ticker: The stock ticker symbol

        Returns:
            Dict with price data or None if failed
        """
        try:
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={self.api_key}"
            response = self.session.get(url, timeout=10)

            if not response.ok:
                logger.warning(f"Bad response for {ticker}: {response.status_code}")
                return None

            data = response.json()

            if 'Global Quote' not in data or not data['Global Quote']:
                logger.warning(f"Invalid data format for {ticker}: {data}")
                return None

            quote = data['Global Quote']

            if '05. price' not in quote or not quote['05. price']:
                logger.warning(f"Missing price for {ticker}")
                return None

            # Get and calculate price metrics
            current_price = float(quote['05. price'])
            previous_close = float(quote['08. previous close']) if '08. previous close' in quote else current_price
            change_percent = float(quote['10. change percent'].strip('%')) if '10. change percent' in quote else 0

            # This doesn't need to save to cache here
            # The cache update will happen later in a proper transaction
            logger.info(f"Successfully fetched price for {ticker}: ${current_price}")

            return {
                'currentPrice': current_price,
                'previousClose': previous_close,
                'changePercent': change_percent,
                'timestamp': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {str(e)}")
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
            cached_stocks = session.query(StockCache).filter(StockCache.ticker.in_(tickers)).all()
            return {stock.ticker: stock.data for stock in cached_stocks if stock.data}
        except Exception as e:
            logger.error(f"Error getting cached tickers: {str(e)}")
            return {}

    def _needs_update(self, cache_data: Optional[Dict[str, Any]]) -> bool:
        """Determine if cache data needs to be updated.

        Args:
            cache_data: Cache data to check

        Returns:
            True if update is needed, False otherwise
        """
        if not cache_data:
            return True

        # Check cache age
        cache_time = cache_data.get('timestamp')
        if not cache_time:
            return True

        # Convert string timestamp to datetime object
        try:
            cache_datetime = datetime.fromisoformat(cache_time)
            # Update if older than 10 minutes during market hours
            if datetime.now() - cache_datetime > timedelta(minutes=10):
                return True
        except (ValueError, TypeError):
            return True

        return False

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
                cache.date = datetime.now().date()
                cache.data = data
            else:
                cache = StockCache(
                    ticker=ticker,
                    date=datetime.now().date(),
                    data=data
                )
                session.add(cache)

        except SQLAlchemyError as e:
            logger.error(f"Database error updating cache for {ticker}: {str(e)}")
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

            for i in range(0, len(tickers), self.batch_size):
                batch_tickers = tickers[i:i + self.batch_size]
                logger.info(
                    f"Updating securities batch {i // self.batch_size + 1}/{(len(tickers) + self.batch_size - 1) // self.batch_size}")

                # Update securities in this batch
                securities = session.query(Security).filter(Security.ticker.in_(batch_tickers)).all()

                for security in securities:
                    ticker_data = price_data.get(security.ticker)
                    if not ticker_data:
                        continue

                    # Update security with new price data
                    try:
                        self._update_security_prices(security, ticker_data)
                        updated_count += 1

                        if security.ticker not in updated_tickers:
                            updated_tickers.append(security.ticker)

                        # Update cache for this ticker
                        self._update_stock_cache(security.ticker, ticker_data, session)

                    except Exception as e:
                        logger.error(f"Error updating security {security.ticker}: {str(e)}")

                logger.info(f"Updated {updated_count} securities so far")

            return {
                'success': True,
                'updated_count': updated_count,
                'tickers_updated': updated_tickers
            }

        except Exception as e:
            logger.error(f"Error in securities update: {str(e)}")
            raise

    def _update_security_prices(self, security: Security, price_data: Dict[str, Any]) -> None:
        """Update a security's price and related metrics.

        Args:
            security: The security to update
            price_data: New price data
        """
        if not price_data:
            return

        # Get values with safety checks
        current_price = float(price_data.get('currentPrice', 0))
        prev_close = float(price_data.get('previousClose', current_price))

        if current_price <= 0:
            logger.warning(f"Invalid price for {security.ticker}: {current_price}")
            return

        # Store original values for comparison
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
                session = db.create_scoped_session()

            try:
                # Query portfolios to update
                if portfolio_id:
                    portfolios = [session.query(Portfolio).get(portfolio_id)]
                    if not portfolios[0]:
                        logger.warning(f"Portfolio {portfolio_id} not found")
                        return
                else:
                    portfolios = session.query(Portfolio).all()

                logger.info(f"Updating totals for {len(portfolios)} portfolios")

                for portfolio in portfolios:
                    securities = session.query(Security).filter_by(portfolio_id=portfolio.id).all()

                    # Calculate aggregated metrics
                    portfolio.total_value = sum(s.total_value or 0 for s in securities)
                    portfolio.day_change = sum(s.value_change or 0 for s in securities)
                    portfolio.total_holdings = len(securities)

                    # Safely calculate percentage
                    base_value = portfolio.total_value - portfolio.day_change
                    portfolio.day_change_pct = (
                                                           portfolio.day_change / base_value) * 100 if base_value and base_value != 0 else 0

                    # Calculate total gain
                    total_cost = sum((s.amount_owned or 0) * (s.purchase_price or 0) for s in securities)
                    portfolio.total_gain = portfolio.total_value - total_cost
                    portfolio.total_gain_pct = ((portfolio.total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

                    # Update the last updated timestamp
                    portfolio.updated_at = datetime.utcnow()

                    logger.info(f"Updated portfolio {portfolio.id}: Value ${portfolio.total_value:.2f}")

                # Only commit if we created our own session
                if not use_provided_session:
                    session.commit()

            except Exception as e:
                if not use_provided_session:
                    session.rollback()
                raise e

            finally:
                if not use_provided_session:
                    session.close()

        except Exception as e:
            logger.error(f"Error updating portfolio totals: {str(e)}")

    def _invalidate_risk_cache(self, portfolio_id: int, session=None) -> None:
        """Invalidate risk analysis cache for a portfolio.

        Args:
            portfolio_id: Portfolio ID to invalidate
            session: Database session to use
        """
        try:
            # Use provided session or create a new one
            use_provided_session = session is not None
            if not use_provided_session:
                session = db.create_scoped_session()

            try:
                cache = session.query(RiskAnalysisCache).filter_by(portfolio_id=portfolio_id).first()
                if cache:
                    session.delete(cache)
                    logger.info(f"Invalidated risk cache for portfolio {portfolio_id}")

                # Only commit if we created our own session
                if not use_provided_session:
                    session.commit()

            except Exception as e:
                if not use_provided_session:
                    session.rollback()
                raise e

            finally:
                if not use_provided_session:
                    session.close()

        except Exception as e:
            logger.error(f"Error invalidating risk cache: {str(e)}")