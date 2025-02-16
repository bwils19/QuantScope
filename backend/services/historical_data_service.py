import os
from datetime import datetime, timedelta
import logging

import requests
from sqlalchemy import func
from backend import db
from backend.models import Security, SecurityHistoricalData, HistoricalDataUpdateLog
from backend.services.market.market_utils import MarketUtils
from backend.services.market.api_client import AlphaVantageClient

logger = logging.getLogger(__name__)


class HistoricalDataService:
    def __init__(self):
        self.market_utils = MarketUtils()
        self.api_client = AlphaVantageClient(os.getenv('ALPHA_VANTAGE_KEY'))

    def get_tickers_needing_update(self):
        """Get list of tickers that need updating"""
        try:
            # Get last trading day
            last_trading_day = self.market_utils.get_last_trading_day()

            # Get all tickers and their latest data
            latest_data = db.session.query(
                SecurityHistoricalData.ticker,
                func.max(SecurityHistoricalData.date).label('latest_date')
            ).group_by(SecurityHistoricalData.ticker).all()

            # Get unique tickers from securities table
            active_tickers = db.session.query(Security.ticker).distinct().all()
            active_tickers = set(t[0] for t in active_tickers)

            tickers_to_update = []
            for ticker, latest_date in latest_data:
                if ticker in active_tickers and latest_date < last_trading_day:
                    tickers_to_update.append((ticker, latest_date))

            # Add tickers with no historical data
            missing_tickers = active_tickers - set(t[0] for t in latest_data)
            tickers_to_update.extend([(t, None) for t in missing_tickers])

            return tickers_to_update

        except Exception as e:
            logger.error(f"Error getting tickers for update: {str(e)}")
            return []

    def process_historical_data(self, ticker, time_series_data, start_date=None):
        """Process historical data for a ticker"""
        try:
            records_added = 0

            for date_str, values in time_series_data.items():
                date = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Skip if before start_date
                if start_date and date <= start_date:
                    continue

                # Check if record already exists
                existing_record = SecurityHistoricalData.query.filter_by(
                    ticker=ticker,
                    date=date
                ).first()

                if not existing_record:
                    hist_data = SecurityHistoricalData(
                        ticker=ticker,
                        date=date,
                        open_price=float(values['1. open']),
                        high_price=float(values['2. high']),
                        low_price=float(values['3. low']),
                        close_price=float(values['4. close']),
                        adjusted_close=float(values['5. adjusted close']),
                        volume=int(values['6. volume']),
                        updated_at=datetime.now()
                    )
                    db.session.add(hist_data)
                    records_added += 1

            return records_added

        except Exception as e:
            logger.error(f"Error processing data for {ticker}: {str(e)}")
            return 0

    def update_historical_data(self):
        """Update historical data for all tickers"""
        try:
            # Check if we should fetch market data
            should_fetch, reason = self.market_utils.should_fetch_market_data()
            if not should_fetch:
                logger.info(f"Skipping update: {reason}")
                return {
                    'success': True,
                    'message': reason,
                    'tickers_updated': 0,
                    'records_added': 0
                }

            # Get tickers needing updates
            tickers_to_update = self.get_tickers_needing_update()
            if not tickers_to_update:
                logger.info("All tickers are up to date")
                return {
                    'success': True,
                    'message': 'All tickers up to date',
                    'tickers_updated': 0,
                    'records_added': 0
                }

            logger.info(f"Found {len(tickers_to_update)} tickers needing updates")

            # Create log entry
            log_entry = HistoricalDataUpdateLog(
                status='started',
                tickers_updated=0,
                records_added=0
            )
            db.session.add(log_entry)
            db.session.commit()

            total_records_added = 0
            total_tickers_updated = 0

            for ticker, latest_date in tickers_to_update:
                try:
                    logger.info(f"Processing {ticker} (Latest data: {latest_date})")

                    time_series_data = self.api_client.fetch_daily_data(ticker)
                    if not time_series_data:
                        continue

                    records_added = self.process_historical_data(
                        ticker,
                        time_series_data,
                        latest_date
                    )

                    if records_added > 0:
                        total_records_added += records_added
                        total_tickers_updated += 1

                    db.session.commit()

                except Exception as e:
                    logger.error(f"Error updating {ticker}: {str(e)}")
                    db.session.rollback()
                    continue

            # Update log entry
            log_entry.status = 'completed'
            log_entry.tickers_updated = total_tickers_updated
            log_entry.records_added = total_records_added
            db.session.commit()

            return {
                'success': True,
                'message': 'Update completed successfully',
                'tickers_updated': total_tickers_updated,
                'records_added': total_records_added
            }

        except Exception as e:
            logger.error(f"Error in update_historical_data: {str(e)}")
            if 'log_entry' in locals():
                log_entry.status = 'failed'
                log_entry.error = str(e)
                db.session.commit()
            return {
                'success': False,
                'message': str(e),
                'tickers_updated': 0,
                'records_added': 0
            }

    def fetch_historical_data(self, ticker, start_date=None, end_date=None):
        """Fetch historical data for a ticker"""
        try:
            print(f"Fetching historical data for {ticker} from {start_date} to {end_date}")

            url = (
                f"https://www.alphavantage.co/query?"
                f"function=TIME_SERIES_DAILY_ADJUSTED&"
                f"symbol={ticker}&outputsize=full&"
                f"apikey={self.api_key}"
            )

            print(f"Making API request for {ticker}...")
            response = requests.get(url)

            # Print raw response for debugging
            print(f"Response status code: {response.status_code}")
            print(f"Response headers: {response.headers}")

            # Check response status
            if response.status_code != 200:
                print(f"API request failed for {ticker}: Status {response.status_code}")
                return None

            data = response.json()

            # Print first part of response data for debugging
            print(f"First part of response data: {str(data)[:500]}")

            # Check for API error messages
            if 'Error Message' in data:
                print(f"API error for {ticker}: {data['Error Message']}")
                return None

            if 'Time Series (Daily)' not in data:
                print(f"No daily time series data found for {ticker}")
                print(f"API Response keys: {data.keys()}")
                return None

            processed_data = []
            time_series = data['Time Series (Daily)']

            for date_str, values in time_series.items():
                date = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Skip if outside date range
                if start_date and date < start_date:
                    continue
                if end_date and date > end_date:
                    continue

                try:
                    processed_data.append({
                        'date': date,
                        'open_price': float(values['1. open']),
                        'high_price': float(values['2. high']),
                        'low_price': float(values['3. low']),
                        'close_price': float(values['4. close']),
                        'adjusted_close': float(values['5. adjusted close']),
                        'volume': int(values['6. volume'])
                    })
                except (ValueError, KeyError) as e:
                    print(f"Error processing data point for {ticker} on {date_str}: {e}")
                    continue

            return processed_data

        except requests.RequestException as e:
            print(f"Network error fetching data for {ticker}: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error fetching historical data for {ticker}: {e}")
            return None
