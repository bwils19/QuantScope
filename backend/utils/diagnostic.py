import logging
from datetime import datetime
from backend.models import SecurityHistoricalData, StockCache, Security
from backend import db

logger = logging.getLogger('app')


def check_date_issues():
    """Check for issues with dates in the database"""
    logger.info("Running date diagnostics...")

    # Check for future dates in historical data
    today = datetime.utcnow().date()
    future_records = SecurityHistoricalData.query.filter(
        SecurityHistoricalData.date > today
    ).limit(10).all()

    if future_records:
        logger.error(f"Found {len(future_records)} historical data records with future dates:")
        for record in future_records:
            logger.error(f"  - {record.ticker}: {record.date} (ID: {record.id})")
    else:
        logger.info("No future dates found in historical data")

    # Check StockCache dates
    future_cache = StockCache.query.filter(
        StockCache.date > today
    ).limit(10).all()

    if future_cache:
        logger.error(f"Found {len(future_cache)} cache records with future dates:")
        for cache in future_cache:
            logger.error(f"  - {cache.ticker}: {cache.date} (ID: {cache.id})")
    else:
        logger.info("No future dates found in cache data")

    # Check for securities with zero prices
    zero_price_securities = Security.query.filter(
        Security.current_price == 0
    ).count()

    if zero_price_securities > 0:
        logger.error(f"Found {zero_price_securities} securities with zero prices")

        # Sample some zero-price securities
        samples = Security.query.filter(
            Security.current_price == 0
        ).limit(5).all()

        for security in samples:
            # logger.error(f"  - {security.ticker}: portfolio_id={security.portfolio_id}, amount={security.amount_owned}")
            logger.error(f"  - {security.ticker}: zero price detected")

            # Check if historical data exists for this security
            hist_data = SecurityHistoricalData.query.filter_by(
                ticker=security.ticker
            ).order_by(SecurityHistoricalData.date.desc()).first()

            if hist_data:
                logger.error(
                    f"    Historical data exists: latest_date={hist_data.date}, price=${hist_data.close_price}")
            else:
                logger.error(f"    No historical data found")

            # Check cache
            cache = StockCache.query.filter_by(ticker=security.ticker).first()
            if cache:
                logger.error(f"    Cache exists: date={cache.date}, price=${cache.data.get('currentPrice', 'N/A')}")
            else:
                logger.error(f"    No cache found")