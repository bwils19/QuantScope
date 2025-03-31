#!/usr/bin/env python3
"""
Script to rebuild the securities table with complete information from Alpha Vantage API.
This will ensure all securities have proper current_price, previous_close, and metadata.
"""

import os
import time
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import after environment variables are loaded
from backend import db
from backend.app import create_app  # Correct import for create_app
from backend.models import Security, SecurityHistoricalData, SecurityMetadata
from backend.services.market.api_client import AlphaVantageClient

def update_security_data(security, api_client):
    """Update a security with complete data from Alpha Vantage API"""
    ticker = security.ticker
    logger.info(f"Processing {ticker}...")
    
    # Step 1: Get company overview data
    overview = api_client.fetch_security_overview(ticker)
    if overview:
        logger.info(f"Got overview data for {ticker}")
        
        # Update security with overview data
        security.name = overview.get('name', security.name)
        security.exchange = overview.get('exchange', security.exchange)
        security.asset_type = overview.get('asset_type', 'Equity')
        security.sector = overview.get('sector', '')
        security.currency = overview.get('currency', 'USD')
        
        # Also update or create SecurityMetadata
        metadata = SecurityMetadata.query.filter_by(ticker=ticker).first()
        if not metadata:
            metadata = SecurityMetadata(ticker=ticker)
            db.session.add(metadata)
        
        metadata.sector = overview.get('sector', '')
        metadata.industry = overview.get('industry', '')
        metadata.asset_type = overview.get('asset_type', 'Equity')
        metadata.currency = overview.get('currency', 'USD')
        metadata.exchange = overview.get('exchange', '')
        metadata.last_updated = datetime.utcnow()
    else:
        logger.warning(f"Could not get overview data for {ticker}")
    
    # Step 2: Get daily price data
    daily_data = api_client.fetch_daily_data(ticker)
    if daily_data:
        logger.info(f"Got daily price data for {ticker}")
        
        # Get the two most recent days
        sorted_dates = sorted(daily_data.keys(), reverse=True)
        if len(sorted_dates) >= 2:
            latest_date = sorted_dates[0]
            previous_date = sorted_dates[1]
            
            latest_price = float(daily_data[latest_date]['4. close'])
            previous_price = float(daily_data[previous_date]['4. close'])
            
            # Update security with price data
            security.current_price = latest_price
            security.previous_close = previous_price
            security.updated_at = datetime.utcnow()
            
            logger.info(f"Updated {ticker} with current_price={latest_price}, previous_close={previous_price}")
            
            # Also ensure we have historical data entries
            for date_str in sorted_dates[:30]:  # Store last 30 days
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                values = daily_data[date_str]
                
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
                        updated_at=datetime.utcnow()
                    )
                    db.session.add(hist_data)
        else:
            logger.warning(f"Not enough daily data for {ticker}")
    else:
        logger.warning(f"Could not get daily price data for {ticker}")
    
    return True

def main():
    """Main function to update all securities"""
    app = create_app()
    with app.app_context():
        # Get API key
        api_key = os.getenv('ALPHA_VANTAGE_KEY')
        if not api_key:
            logger.error("No Alpha Vantage API key found in environment variables")
            return
        
        # Create API client
        api_client = AlphaVantageClient(api_key)
        
        # Get all securities
        securities = Security.query.all()
        logger.info(f"Found {len(securities)} securities to update")
        
        # Process each security
        success_count = 0
        error_count = 0
        
        for i, security in enumerate(securities):
            try:
                logger.info(f"Processing {i+1}/{len(securities)}: {security.ticker}")
                if update_security_data(security, api_client):
                    success_count += 1
                
                # Commit after each security to avoid losing all work if one fails
                db.session.commit()
                logger.info(f"Committed changes for {security.ticker}")
                
                # Sleep to respect API rate limits (5 calls per minute for free tier)
                if (i + 1) % 5 == 0:
                    logger.info("Sleeping for 60 seconds to respect API rate limits...")
                    time.sleep(60)
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing {security.ticker}: {str(e)}")
                db.session.rollback()
                
                # Still sleep to respect rate limits even on error
                time.sleep(12)
        
        logger.info(f"Completed processing {len(securities)} securities")
        logger.info(f"Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()