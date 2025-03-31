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
import requests

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

# Counter for API calls to manage rate limiting
api_call_count = 0
RATE_LIMIT = 75  # Premium tier: 75 calls per minute
last_reset_time = datetime.now()

def reset_rate_limit_if_needed():
    """Reset the API call counter if a minute has passed"""
    global api_call_count, last_reset_time
    now = datetime.now()
    if (now - last_reset_time).total_seconds() >= 60:
        logger.info(f"Resetting API call counter. Previous count: {api_call_count}")
        api_call_count = 0
        last_reset_time = now

def increment_api_call_counter():
    """Increment the API call counter and sleep if needed"""
    global api_call_count
    reset_rate_limit_if_needed()
    
    api_call_count += 1
    logger.debug(f"API call count: {api_call_count}/{RATE_LIMIT}")
    
    if api_call_count >= RATE_LIMIT:
        logger.info(f"Reached API rate limit of {RATE_LIMIT} calls. Sleeping for 60 seconds...")
        time.sleep(60)
        api_call_count = 0
        last_reset_time = datetime.now()

def fetch_company_overview(ticker, api_key):
    """Fetch company overview data directly"""
    increment_api_call_counter()
    
    try:
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch overview for {ticker}: {response.status_code}")
            return None
        
        data = response.json()
        
        # Check for error messages
        if "Error Message" in data:
            logger.error(f"API error for {ticker}: {data['Error Message']}")
            return None
        
        # Check if we got valid data (Symbol field should be present)
        if "Symbol" not in data:
            logger.warning(f"No valid overview data for {ticker}")
            return None
            
        logger.info(f"Got overview data for {ticker}: {data.get('Name', 'N/A')}")
        
        return {
            'ticker': ticker,
            'name': data.get('Name'),
            'sector': data.get('Sector'),
            'industry': data.get('Industry'),
            'asset_type': data.get('AssetType', 'Equity'),
            'currency': data.get('Currency', 'USD'),
            'exchange': data.get('Exchange'),
            'last_updated': datetime.utcnow()
        }
    
    except Exception as e:
        logger.error(f"Error fetching overview for {ticker}: {str(e)}")
        return None

def fetch_daily_data(ticker, api_key):
    """Fetch daily price data directly"""
    increment_api_call_counter()
    
    try:
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={ticker}&outputsize=compact&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch daily data for {ticker}: {response.status_code}")
            return None
        
        data = response.json()
        
        # Check for error messages
        if "Error Message" in data:
            logger.error(f"API error for {ticker}: {data['Error Message']}")
            return None
        
        # Check if we got valid data
        if "Time Series (Daily)" not in data:
            logger.warning(f"No daily time series data found for {ticker}")
            return None
        
        return data['Time Series (Daily)']
    
    except Exception as e:
        logger.error(f"Error fetching daily data for {ticker}: {str(e)}")
        return None

def update_security_data(security, api_key):
    """Update a security with complete data from Alpha Vantage API"""
    ticker = security.ticker
    logger.info(f"Processing {ticker}...")
    
    # Step 1: Get company overview data
    overview = fetch_company_overview(ticker, api_key)
    if overview:
        # Update security with overview data
        if overview.get('name'):
            security.name = overview.get('name')
            logger.info(f"Updated name for {ticker} to: {security.name}")
        
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
    daily_data = fetch_daily_data(ticker, api_key)
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
        
        # Get all securities
        securities = Security.query.all()
        logger.info(f"Found {len(securities)} securities to update")
        
        # Process each security
        success_count = 0
        error_count = 0
        
        for i, security in enumerate(securities):
            try:
                logger.info(f"Processing {i+1}/{len(securities)}: {security.ticker}")
                if update_security_data(security, api_key):
                    success_count += 1
                
                # Commit after each security to avoid losing all work if one fails
                db.session.commit()
                logger.info(f"Committed changes for {security.ticker}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing {security.ticker}: {str(e)}")
                db.session.rollback()
        
        logger.info(f"Completed processing {len(securities)} securities")
        logger.info(f"Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()