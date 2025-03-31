#!/usr/bin/env python3
"""
Script to specifically fix previous_close values in the securities table.
This ensures that previous_close values are properly set from historical data.
"""

import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import after environment variables are loaded
from backend import db
from backend.app import create_app  # Correct import for create_app
from backend.models import Security, SecurityHistoricalData

def fix_previous_close_values():
    """Fix previous_close values for all securities using historical data"""
    # Get all securities
    securities = Security.query.all()
    logger.info(f"Found {len(securities)} securities to check")
    
    fixed_count = 0
    error_count = 0
    
    for security in securities:
        try:
            ticker = security.ticker
            logger.info(f"Processing {ticker}...")
            
            # Skip if both current_price and previous_close are already set and different
            if security.current_price and security.previous_close and security.current_price != security.previous_close:
                logger.info(f"Security {ticker} already has different current_price and previous_close values")
                continue
            
            # Get the two most recent historical data points
            historical_data = SecurityHistoricalData.query.filter_by(ticker=ticker) \
                .order_by(SecurityHistoricalData.date.desc()) \
                .limit(2) \
                .all()
            
            if len(historical_data) >= 2:
                # Use the most recent day for current_price and the day before for previous_close
                current_price = historical_data[0].close_price
                previous_close = historical_data[1].close_price
                
                # Update the security
                security.current_price = current_price
                security.previous_close = previous_close
                security.updated_at = datetime.utcnow()
                
                logger.info(f"Updated {ticker}: current_price={current_price}, previous_close={previous_close}")
                fixed_count += 1
            else:
                logger.warning(f"Not enough historical data for {ticker}")
                error_count += 1
        
        except Exception as e:
            logger.error(f"Error processing {security.ticker}: {str(e)}")
            error_count += 1
    
    # Commit all changes
    db.session.commit()
    logger.info(f"Fixed {fixed_count} securities, {error_count} errors")
    return fixed_count, error_count

def main():
    """Main function"""
    app = create_app()
    with app.app_context():
        logger.info("Starting to fix previous_close values...")
        fixed_count, error_count = fix_previous_close_values()
        logger.info(f"Completed. Fixed: {fixed_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()