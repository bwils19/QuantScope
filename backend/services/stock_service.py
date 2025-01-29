# stock_service
from datetime import datetime, timedelta
import pytz
from sqlalchemy import func, distinct
from backend import db
from backend.models import Security, Portfolio, StockCache
import requests
import time
import os


def is_market_open():
    """Check if US market is open"""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)

    # US Market Holidays 2025 for now, need to make more dynamic later
    holidays_2025 = {
        datetime(2025, 1, 1),   # New Year's Day
        datetime(2025, 1, 20),  # Martin Luther King Jr. Day
        datetime(2025, 2, 17),  # Presidents Day
        datetime(2025, 4, 18),  # Good Friday
        datetime(2025, 5, 26),  # Memorial Day
        datetime(2025, 7, 4),   # Independence Day
        datetime(2025, 9, 1),   # Labor Day
        datetime(2025, 11, 27),  # Thanksgiving Day
        datetime(2025, 12, 25),  # Christmas Day
    }

    # Check if today is a holiday
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if today in holidays_2025:
        return False

    # Market hours are 9:30 AM to 4:00 PM Eastern, Monday to Friday
    market_start = now.replace(hour=9, minute=30, second=0, microsecond=0).time()
    market_end = now.replace(hour=16, minute=0, second=0, microsecond=0).time()

    return (now.weekday() < 5 and  # Monday = 0, Friday = 4
            market_start <= now.time() <= market_end)


def update_prices():
    """Update prices for all unique securities twice daily"""
    if not is_market_open():
        return

    # Use the current_app context to ensure everything is set
    from flask import current_app
    with current_app.app_context():
        session = None
        try:
            session = db.session  # or a custom session with SessionLocal if needed

            # Your existing logic with session.begin() or explicit commits
            with session.begin():
                unique_tickers = session.query(distinct(Security.ticker)).all()
                tickers = [t[0] for t in unique_tickers]
                api_key = os.getenv('ALPHA_VANTAGE_KEY')

            for ticker in tickers:
                try:
                    # Check cache first
                    cache = StockCache.query.filter_by(ticker=ticker).first()
                    if cache and not _should_update_cache(cache):
                        continue

                    # Fetch new price data
                    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
                    response = requests.get(url)
                    data = response.json()

                    if 'Global Quote' in data:
                        quote = data['Global Quote']
                        current_price = float(quote['05. price'])
                        prev_close = float(quote['08. previous close'])

                        # Update cache
                        if not cache:
                            cache = StockCache(ticker=ticker)

                        cache.current_price = current_price
                        cache.previous_close = prev_close
                        cache.change_percent = float(quote['10. change percent'].rstrip('%'))
                        cache.last_update = datetime.utcnow()

                        session.add(cache)

                    time.sleep(12)  # Rate limit compliance

                except Exception as e:
                    print(f"Error in price update task: {str(e)}")
                    if session is not None:
                        session.rollback()
        finally:
            if session is not None:
                session.close()


def _should_update_cache(cache):
    """Determine if cache needs update based on market hours"""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)

    if not cache.last_update:
        return True

    # Convert cache time to NY timezone
    cache_time = cache.last_update.astimezone(ny_tz)

    # Update if last update was not today
    if cache_time.date() != now.date():
        return True

    # Update at market open and mid-day
    market_open = now.replace(hour=9, minute=30)
    mid_day = now.replace(hour=13, minute=0)

    return (
            (now >= market_open and cache_time < market_open) or
            (now >= mid_day and cache_time < mid_day)
    )


def get_cached_prices(tickers):
    """Get prices from cache for multiple tickers"""
    return StockCache.query.filter(
        StockCache.ticker.in_(tickers)
    ).all()


def update_portfolio_totals(portfolio_id):
    """Update portfolio calculations using cached prices"""
    try:
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            return

        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()
        cached_prices = get_cached_prices([s.ticker for s in securities])
        price_map = {p.ticker: p for p in cached_prices}

        total_value = 0
        total_change = 0

        for security in securities:
            price_data = price_map.get(security.ticker)
            if price_data:
                security.current_price = price_data.current_price
                security.total_value = security.amount_owned * price_data.current_price
                security.value_change = security.amount_owned * (price_data.current_price - price_data.previous_close)

                total_value += security.total_value
                total_change += security.value_change

        portfolio.total_value = total_value
        portfolio.day_change = total_change

        if total_value != total_change:
            portfolio.day_change_pct = (total_change / (total_value - total_change)) * 100

        db.session.commit()

    except Exception as e:
        print(f"Error updating portfolio totals: {str(e)}")
        db.session.rollback()