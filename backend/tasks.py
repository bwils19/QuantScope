# tasks.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import time
import pytz
import requests
from backend import db
from backend.models import Portfolio, Security, StockCache
import os

from backend.services.stock_service import update_prices, is_market_open
from backend.services.historical_data_service import HistoricalDataService


def update_portfolio_prices():
    """Update prices for all securities in active portfolios"""
    print(f"Starting price update at {datetime.now()}")
    if not is_market_open():
        print("Market is closed, skipping price update")
        return

    try:
        session = db.create_scoped_session()

        with session.begin():
            # Get unique tickers and their associated users from active portfolios
            securities_info = (
                db.session.query(
                    Security.ticker,
                    db.func.array_agg(db.distinct(Portfolio.user_id)).label('user_ids')
                )
                .join(Portfolio)
                .group_by(Security.ticker)
                .all()
            )

            print(f"Found portfolios with these tickers:")
            for ticker, user_ids in securities_info:
                print(f"- {ticker}: owned in {len(user_ids)} portfolios")

            if not securities_info:
                print("No securities found in any portfolios")
                return

            api_key = os.getenv('ALPHA_VANTAGE_KEY')

            for ticker, user_ids in securities_info:
                try:
                    print(f"Updating {ticker} (owned by {len(user_ids)} users)")

                    # Fetch current price from Alpha Vantage
                    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
                    response = requests.get(url)
                    data = response.json()

                    if 'Global Quote' in data:
                        quote = data['Global Quote']
                        current_price = float(quote['05. price'])
                        prev_close = float(quote['08. previous close'])

                        # Update cache
                        cache = StockCache.query.filter_by(ticker=ticker).first()
                        if not cache:
                            cache = StockCache(ticker=ticker)

                        cache.date = datetime.utcnow().date()
                        cache.data = {
                            'currentPrice': current_price,
                            'previousClose': prev_close,
                            'changePercent': float(quote['10. change percent'].rstrip('%'))
                        }

                        # Update all securities with this ticker
                        securities = Security.query.filter_by(ticker=ticker).all()
                        for security in securities:
                            if security.amount_owned is None:
                                print(f"Warning: {security.ticker} has None for amount_owned")
                                continue

                            old_value = security.total_value or 0  # Use 0 if None

                            try:
                                security.current_price = current_price
                                security.total_value = security.amount_owned * current_price
                                security.value_change = security.amount_owned * (current_price - prev_close)

                                # Add null checks for division
                                base_value = (
                                            old_value - security.value_change) if old_value != security.value_change else 1
                                security.value_change_pct = (
                                                                        security.value_change / base_value) * 100 if base_value != 0 else 0

                                # Add null check for purchase price
                                if security.purchase_price is not None and security.purchase_price != 0:
                                    security.total_gain = security.total_value - (
                                            security.amount_owned * security.purchase_price)
                                    security.total_gain_pct = ((security.total_value / (
                                            security.amount_owned * security.purchase_price)) - 1) * 100
                                else:
                                    security.total_gain = 0
                                    security.total_gain_pct = 0

                                print(f"Updated {security.ticker} successfully")

                            except Exception as e:
                                print(f"Error updating {security.ticker}: {str(e)}")
                                print(
                                    f"Debug values - amount: {security.amount_owned}, price: {current_price}, prev_close: {prev_close}")
                                continue

                        print(f"Successfully updated {ticker}")
                    else:
                        print(f"No quote data received for {ticker}")

                    # API rate limits
                    time.sleep(3)  # Alpha Vantage free tier limit is 5 calls per minute - upgraded to premium tho

                except Exception as e:
                    print(f"Error updating (TASKS.PY SCRIPT) {ticker}: {str(e)}")
                    continue

            # Update portfolio totals with explicit transaction
            with session.begin_nested():
                portfolios = Portfolio.query.all()
                for portfolio in portfolios:
                    print(f"Updating portfolio {portfolio.name}")
                    securities = portfolio.securities
                    old_total = portfolio.total_value

                    portfolio.total_value = sum(s.total_value for s in securities)
                    portfolio.day_change = sum(s.value_change for s in securities)
                    if old_total != portfolio.total_value:
                        print(
                            f"Portfolio {portfolio.name} value changed: ${old_total:,.2f} -> "
                            f"${portfolio.total_value:,.2f}")

                    portfolio.day_change_pct = (portfolio.day_change /
                                                (portfolio.total_value - portfolio.day_change)) * 100

                    total_cost = sum(s.amount_owned * s.purchase_price for s in securities)
                    portfolio.total_gain = portfolio.total_value - total_cost
                    portfolio.total_gain_pct = ((portfolio.total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

                try:
                    session.commit()
                    print("Successfully committed all portfolio updates")
                except Exception as e:
                    print(f"Error committing portfolio updates: {e}")
                    session.rollback()
                    raise

            print("Completed all price updates")
        session.close()

    except Exception as e:
        print(f"Error in price update task: {str(e)}")
        session.rollback()
        session.close()


def init_scheduler(app):
    from apscheduler.schedulers.background import BackgroundScheduler
    from backend.services.stock_service import update_prices

    scheduler = BackgroundScheduler()

    # Run twice daily during market hours
    scheduler.add_job(
        func=update_prices,
        trigger=CronTrigger(
            day_of_week='mon-fri',
            hour='9,13',  # Run at market open (9:30 AM) and mid-day (1 PM)
            minute='30',
            timezone=pytz.timezone('America/New_York')
        ),
        id='update_prices',
        name='Update security prices twice daily',
        coalesce=True,
        max_instances=1
    )

    # historical data pull
    historical_data_service = HistoricalDataService()
    scheduler.add_job(
        func=historical_data_service.update_historical_data,
        trigger=CronTrigger(
            day_of_week='mon-fri',
            hour='16',  # Run after market close to get close prices
            minute='30',
            timezone=pytz.timezone('America/New_York')
        ),
        id='update_historical_data',
        name='Update historical price data',
        coalesce=True,
        max_instances=1
    )

    scheduler.start()
    return scheduler
