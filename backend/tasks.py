from backend.celery_app import celery as app
# backend/tasks.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import logging
from datetime import datetime
import time

from celery import group
from celery.contrib.abortable import AbortableTask
from backend import db
from backend.models import Security, SecurityHistoricalData, HistoricalDataUpdateLog, StockCache
from backend.services.price_update_service import PriceUpdateService
from backend.services.historical_data_service import HistoricalDataService
from backend.services.stock_service import is_market_open
from celery import shared_task


# Configure logging
logger = logging.getLogger('scheduler')


#  CELERY TASKS

@app.task(bind=True, max_retries=3, rate_limit='75/m')
def update_ticker_price(ticker, force=False):
    """Update price for a single ticker with rate limiting"""
    try:
        task_logger = logging.getLogger('celery.tasks')
        task_logger.info(f"Updating price for {ticker}")

        service = PriceUpdateService()
        result = service.update_price_for_ticker(ticker, force)

        # Update security record with new price
        if result and result.get('success'):
            try:
                security = Security.query.filter_by(ticker=ticker).first()
                if security:
                    security.current_price = result.get('current_price')
                    security.previous_close = result.get('previous_close')
                    security.updated_at = datetime.utcnow()
                    db.session.commit()
            except Exception as db_error:
                task_logger.error(f"Database error updating {ticker}: {str(db_error)}")

        return result
    except Exception as exc:
        task_logger = logging.getLogger('celery.tasks')
        task_logger.error(f"Error updating price for {ticker}: {exc}")
        # Use the task directly, not self
        self.retry(exc=exc, countdown=60)


@shared_task
def update_batch_prices(tickers, force=False):
    """Update a batch of tickers (respecting API rate limits)"""
    task_logger = logging.getLogger('celery.tasks')
    task_logger.info(f"Processing batch of {len(tickers)} tickers")

    results = {
        'updated': 0,
        'failed': 0,
        'tickers': []
    }

    # Process each ticker with proper rate limiting
    for ticker in tickers:
        try:
            result = update_ticker_price(ticker, force)

            if result and result.get('success'):
                results['updated'] += 1
                results['tickers'].append(ticker)
            else:
                results['failed'] += 1

            # Small pause to avoid hitting rate limits
            time.sleep(0.8)  # ~75 requests per minute

        except Exception as e:
            task_logger.error(f"Error updating {ticker}: {str(e)}")
            results['failed'] += 1

    return results


@shared_task
def scheduled_price_update():
    """Update prices for all securities in active portfolios with rate limiting"""
    task_logger = logging.getLogger('celery.tasks')
    task_logger.info(f"Starting scheduled price update at {datetime.now()}")

    # Skip updates when market is closed
    if not is_market_open():
        task_logger.info("Market is closed, skipping price update")
        return {"success": False, "message": "Market closed"}

    try:
        # Get all tickers that need updating
        tickers = db.session.query(Security.ticker).distinct().all()
        tickers = [t[0] for t in tickers]

        # Create batches of 75 tickers (API rate limit)
        batch_size = 75
        batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

        task_logger.info(f"Processing {len(tickers)} tickers in {len(batches)} batches")

        results = {'updated': 0, 'failed': 0, 'batches_completed': 0}

        for i, batch in enumerate(batches):
            batch_result = update_batch_prices.delay(batch)
            batch_data = batch_result.get(timeout=240)  # Wait up to 4 minutes

            # Combine results
            results['updated'] += batch_data.get('updated', 0)
            results['failed'] += batch_data.get('failed', 0)
            results['batches_completed'] += 1

            # Rate limiting between batches
            if i < len(batches) - 1:
                task_logger.info("Waiting 60 seconds before next batch...")
                time.sleep(60)

        return {
            "success": True,
            "updated_count": results['updated'],
            "failed_count": results['failed'],
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        task_logger.error(f"Error in price update task: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task
def save_closing_prices():
    """Save closing prices at market close"""
    task_logger = logging.getLogger('celery.tasks')
    task_logger.info(f"Running end-of-day price update at {datetime.now()}")

    try:
        # Force update all prices to get closing values
        tickers = db.session.query(Security.ticker).distinct().all()
        tickers = [t[0] for t in tickers]

        # Create batches of 75 tickers (API rate limit)
        batch_size = 75
        batches = [tickers[i:i + batch_size] for i in range(0, len(tickers), batch_size)]

        results = {'updated': 0, 'failed': 0}

        for i, batch in enumerate(batches):
            batch_result = update_batch_prices.delay(batch, force=True)
            batch_data = batch_result.get(timeout=240)

            # Combine results
            results['updated'] += batch_data.get('updated', 0)
            results['failed'] += batch_data.get('failed', 0)

            # Rate limiting between batches
            if i < len(batches) - 1:
                time.sleep(60)

        # Update stock cache timestamps
        today = datetime.now().date()
        for ticker in tickers:
            cache = StockCache.query.filter_by(ticker=ticker).first()
            if cache:
                cache.date = today

        db.session.commit()

        return {
            "success": True,
            "updated_count": results['updated'],
            "failed_count": results['failed'],
            "message": "End-of-day update completed",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        task_logger.error(f"Error in end-of-day update: {str(e)}")
        return {"success": False, "error": str(e)}


@shared_task
def update_historical_data():
    """Add daily closing data to historical record after market close"""
    task_logger = logging.getLogger('celery.tasks')
    task_logger.info(f"Starting historical data update at {datetime.now()}")

    try:
        # Get all securities that need historical data
        tickers = Security.query.with_entities(Security.ticker).distinct().all()
        tickers = [t[0] for t in tickers]

        today = datetime.now().date()
        updated_count = 0

        for ticker in tickers:
            # Check if we already have historical data for today
            existing = SecurityHistoricalData.query.filter_by(
                ticker=ticker, date=today).first()

            if existing:
                continue

            # Get the security record with latest price
            security = Security.query.filter_by(ticker=ticker).first()
            if not security or not security.current_price:
                continue

            # Create new historical record
            historical_data = SecurityHistoricalData(
                ticker=ticker,
                date=today,
                open_price=security.current_price,  # Use current price as approximation
                high_price=security.current_price,
                low_price=security.current_price,
                close_price=security.current_price,
                adjusted_close=security.current_price,
                volume=0,  # Will need to be updated with real data
                updated_at=datetime.utcnow()
            )

            db.session.add(historical_data)
            updated_count += 1

            # Commit in batches to avoid long transactions
            if updated_count % 50 == 0:
                db.session.commit()

        # Final commit
        db.session.commit()

        # Create log entry
        log_entry = HistoricalDataUpdateLog(
            update_time=datetime.utcnow(),
            tickers_updated=len(tickers),
            records_added=updated_count,
            status="success"
        )
        db.session.add(log_entry)
        db.session.commit()

        return {
            "success": True,
            "tickers_updated": len(tickers),
            "records_added": updated_count
        }

    except Exception as e:
        task_logger.error(f"Error updating historical data: {str(e)}")

        # Log the error
        log_entry = HistoricalDataUpdateLog(
            update_time=datetime.utcnow(),
            tickers_updated=0,
            records_added=0,
            status="failed",
            error=str(e)
        )
        db.session.add(log_entry)
        db.session.commit()

        return {
            "success": False,
            "error": str(e)
        }

@shared_task(name='backend.tasks.backfill_historical_prices', bind=True)
def backfill_historical_prices(self, force_update=False):
    """Backfill missing historical prices for securities."""
    logger = logging.getLogger('celery.tasks')
    logger.info(f">>> RUNNING backfill_historical_prices <<<")

    try:
        from backend.app import create_app
        app = create_app()

        with app.app_context():
            logger.info("App context established successfully")

            # Only instantiate this AFTER context is active
            from backend.services.historical_data_service import HistoricalDataService
            service = HistoricalDataService()

            result = service.update_historical_data(force_update=force_update)
            logger.info(f"Backfill complete: {result}")
            return result

    except Exception as e:
        logger.error(f"Error in backfill_historical_prices: {str(e)}", exc_info=True)
        raise self.retry(exc=e, countdown=60)




#  APSCHEDULER FUNCTIONS - not ccurrently using, using celery

def update_portfolio_prices():
    """Update prices for all securities in active portfolios"""
    logger.info(f"Starting scheduled price update at {datetime.now()}")

    # Skip updates when market is closed
    if not is_market_open():
        logger.info("Market is closed, skipping price update")
        return

    try:
        # Use our price update service
        price_service = PriceUpdateService()
        result = price_service.update_all_portfolio_prices()

        if result.get('success', False):
            logger.info(f"Successfully updated {result.get('updated_count', 0)} securities")
            logger.info(f"Failed to update {result.get('failed_count', 0)} securities")
        else:
            logger.error(f"Price update failed: {result.get('error', 'Unknown error')}")

    except Exception as e:
        logger.error(f"Error in price update task: {str(e)}", exc_info=True)


def init_scheduler(app):
    """Initialize the task scheduler with optimal schedule for market hours."""
    try:
        scheduler = BackgroundScheduler()

        # Set up price updates during market hours
        scheduler.add_job(
            func=update_portfolio_prices,
            trigger=CronTrigger(
                day_of_week='mon-fri',  # Weekdays only
                hour='9,10,11,12,13,14,15,16',  # Every hour during market hours (9:30 AM - 4 PM ET)
                minute='0',  # ,15,30,45',  # Every 15 minutes - this is too much, changed to the hour for now.
                timezone=pytz.timezone('America/New_York')
            ),
            id='update_prices',
            name='Update security prices during market hours',
            coalesce=True,
            max_instances=1
        )

        # Historical data pull after market close
        historical_data_service = HistoricalDataService()
        scheduler.add_job(
            func=historical_data_service.update_historical_data,
            trigger=CronTrigger(
                day_of_week='mon-fri',
                hour='16',  # Run after market closes
                minute='30',
                timezone=pytz.timezone('America/New_York')
            ),
            id='update_historical_data',
            name='Update historical price data',
            coalesce=True,
            max_instances=1
        )

        # Add another job for end-of-day portfolio refresh
        scheduler.add_job(
            func=update_portfolio_prices,
            trigger=CronTrigger(
                day_of_week='mon-fri',
                hour='17',  # Run one final update after market closes
                minute='00',
                timezone=pytz.timezone('America/New_York')
            ),
            id='end_of_day_update',
            name='End of day portfolio refresh',
            coalesce=True,
            max_instances=1
        )

        # weekend scheduler
        scheduler.add_job(
            func=update_portfolio_prices,
            trigger=CronTrigger(
                day_of_week='sat,sun',  # Weekend only
                hour='*/10',  # Every 10 hours
                minute='15',  # 15 minutes past the hour
                timezone=pytz.timezone('America/New_York')
            ),
            id='weekend_prices',
            name='Weekend price refresh',
            coalesce=True,
            max_instances=1
        )

        # Start the scheduler with error handling
        try:
            scheduler.start()
            app.logger.info("Scheduler started successfully")
        except Exception as e:
            app.logger.error(f"Failed to start scheduler: {e}")
            # Continue without scheduler rather than crashing the app - which is suuuper annoying
            return None

        def shutdown_scheduler(exception=None):
            try:
                # Only shut down if the scheduler exists and is running
                if scheduler and scheduler.running:
                    scheduler.shutdown()
                    app.logger.info("Scheduler shut down")
            except Exception as e:
                app.logger.error(f"Error shutting down scheduler: {e}")

            app.teardown_appcontext(shutdown_scheduler)

            return scheduler
    except Exception as e:
        app.logger.error(f"Error initializing scheduler: {e}")
        # Return None instead of crashing
        return None

# Explicit task registration
app.register_task(update_ticker_price)
