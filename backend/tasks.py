from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, time
import pytz
import requests
from backend import db
from backend.models import Portfolio, Security, StockCache
import os


def is_market_open():
    """Check if US market is open-  sticking with this for now, will make more elegant in the future"""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)

    # Market hours are 9:30 AM to 4:00 PM Eastern, Monday to Friday
    market_start = time(9, 30)
    market_end = time(16, 0)

    return (now.weekday() < 5 and  # Monday = 0, Friday = 4
            market_start <= now.time() <= market_end)


def update_portfolio_prices():
    """Update prices for all securities in active portfolios"""
    print(f"Starting price update at {datetime.now()}")
    if not is_market_open():
        print("Market is closed, skipping price update")
        return

    try:
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
                        old_value = security.total_value
                        security.current_price = current_price
                        security.total_value = security.amount_owned * current_price
                        security.value_change = security.amount_owned * (current_price - prev_close)
                        security.value_change_pct = (security.value_change / (old_value - security.value_change)) * 100
                        security.unrealized_gain = security.total_value - (
                                    security.amount_owned * security.purchase_price)
                        security.unrealized_gain_pct = ((security.total_value / (
                                    security.amount_owned * security.purchase_price)) - 1) * 100

                    print(f"Successfully updated {ticker}")
                else:
                    print(f"No quote data received for {ticker}")

                # Respect API rate limits
                time.sleep(12)  # Alpha Vantage free tier limit is 5 calls per minute

            except Exception as e:
                print(f"Error updating {ticker}: {str(e)}")
                continue

        # Update portfolio totals with explicit transaction
        with db.session.begin_nested():  # Create a savepoint
            portfolios = Portfolio.query.all()
            for portfolio in portfolios:
                print(f"Updating portfolio {portfolio.name}")  # Debug log
                securities = portfolio.securities
                old_total = portfolio.total_value

                portfolio.total_value = sum(s.total_value for s in securities)
                portfolio.day_change = sum(s.value_change for s in securities)
                if old_total != portfolio.total_value:
                    print(
                        f"Portfolio {portfolio.name} value changed: ${old_total:,.2f} -> ${portfolio.total_value:,.2f}")

                portfolio.day_change_pct = (portfolio.day_change / (portfolio.total_value - portfolio.day_change)) * 100

                total_cost = sum(s.amount_owned * s.purchase_price for s in securities)
                portfolio.unrealized_gain = portfolio.total_value - total_cost
                portfolio.unrealized_gain_pct = ((
                                                             portfolio.total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

            try:
                db.session.commit()
                print("Successfully committed all portfolio updates")
            except Exception as e:
                print(f"Error committing portfolio updates: {e}")
                db.session.rollback()
                raise

        print("Completed all price updates")

    except Exception as e:
        print(f"Error in price update task: {str(e)}")
        db.session.rollback()


def init_scheduler(app):

    scheduler = BackgroundScheduler()

    # Run every 5 minutes during market hours
    scheduler.add_job(
        func=update_portfolio_prices,
        trigger=CronTrigger(
            day_of_week='mon-fri',
            hour='9-16',
            minute='*/5',
            timezone=pytz.timezone('America/New_York')
        ),
        id='update_portfolio_prices',
        name='Update portfolio prices every 5 minutes during market hours',
        coalesce=True,  # Only run once if multiple executions are missed
        max_instances=1  # Only one instance can run at a time
    )

    # Start the scheduler
    scheduler.start()
    return scheduler