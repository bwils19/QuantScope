# backend/tasks.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import logging
from datetime import datetime

from backend.services.price_update_service import PriceUpdateService
from backend.services.historical_data_service import HistoricalDataService
from backend.services.stock_service import is_market_open

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_portfolio_prices():
    """Update prices for all securities in active portfolios"""
    logger.info(f"Starting price update at {datetime.now()}")

    # Skip updates when market is closed
    if not is_market_open():
        logger.info("Market is closed, skipping price update")
        return

    try:
        # Use our new price update service
        price_service = PriceUpdateService()
        result = price_service.update_all_portfolio_prices()

        if result.get('success', False):
            logger.info(f"Successfully updated {result.get('updated_count', 0)} securities")
            logger.info(f"Failed to update {result.get('failed_count', 0)} securities")
            logger.info(f"Update completed in {result.get('elapsed_time', 0):.2f} seconds")
        else:
            logger.error(f"Price update failed: {result.get('error', 'Unknown error')}")
            logger.error(f"Details: {result}")  # Add more detailed logging

    except Exception as e:
        logger.error(f"Error in price update task: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")


def init_scheduler(app):
    """Initialize the task scheduler with optimal schedule for market hours."""
    scheduler = BackgroundScheduler()

    # Set up price updates during market hours
    scheduler.add_job(
        func=update_portfolio_prices,
        trigger=CronTrigger(
            day_of_week='mon-fri',  # Weekdays only
            hour='9,10,11,12,13,14,15,16',  # Every hour during market hours (9:30 AM - 4 PM ET)
            minute='0,15,30,45',  # Every 15 minutes
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
    try:
        scheduler.start()
        app.logger.info("Scheduler started successfully")
    except Exception as e:
        app.logger.error(f"Failed to start scheduler: {e}")

        # Register a teardown to handle app shutdown

    def shutdown_scheduler(exception=None):
        scheduler.shutdown()
        app.logger.info("Scheduler shut down")

    app.teardown_appcontext(shutdown_scheduler)

    scheduler.start()
    return scheduler
