#!/usr/bin/env python3
"""
Script to fix missing company names in the securities table.
This will fetch company information from Alpha Vantage for securities with missing names.
"""

import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import after environment variables are loaded
from backend import db
from backend.app import create_app
from backend.models import Security, SecurityMetadata

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

def fetch_company_info(ticker, api_key):
    """Fetch company information from Alpha Vantage"""
    increment_api_call_counter()
    
    try:
        # First try OVERVIEW endpoint
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch overview for {ticker}: {response.status_code}")
            return None
        
        data = response.json()
        
        # Check if we got valid data (Symbol field should be present)
        if "Symbol" in data and data.get("Name"):
            logger.info(f"Got company name for {ticker} from OVERVIEW: {data.get('Name')}")
            return {
                'name': data.get('Name'),
                'sector': data.get('Sector'),
                'industry': data.get('Industry'),
                'asset_type': data.get('AssetType', 'Equity'),
                'currency': data.get('Currency', 'USD'),
                'exchange': data.get('Exchange')
            }
        
        # If OVERVIEW didn't work, try SYMBOL_SEARCH
        increment_api_call_counter()
        url = f"https://www.alphavantage.co/query?function=SYMBOL_SEARCH&keywords={ticker}&apikey={api_key}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch symbol search for {ticker}: {response.status_code}")
            return None
        
        data = response.json()
        
        if "bestMatches" in data and data["bestMatches"]:
            # Find exact match for ticker
            for match in data["bestMatches"]:
                if match.get("1. symbol") == ticker:
                    logger.info(f"Got company name for {ticker} from SYMBOL_SEARCH: {match.get('2. name')}")
                    return {
                        'name': match.get('2. name'),
                        'exchange': match.get('4. region'),
                        'currency': match.get('8. currency', 'USD'),
                        'asset_type': 'Equity'  # Default
                    }
            
            # If no exact match, use the first match
            if data["bestMatches"]:
                match = data["bestMatches"][0]
                logger.info(f"Using best match for {ticker} from SYMBOL_SEARCH: {match.get('2. name')}")
                return {
                    'name': match.get('2. name'),
                    'exchange': match.get('4. region'),
                    'currency': match.get('8. currency', 'USD'),
                    'asset_type': 'Equity'  # Default
                }
        
        logger.warning(f"No company information found for {ticker}")
        return None
    
    except Exception as e:
        logger.error(f"Error fetching company info for {ticker}: {str(e)}")
        return None

def fix_missing_names():
    """Fix missing company names in the securities table"""
    # Get securities with missing or default names
    securities = Security.query.filter(
        (Security.name == None) | 
        (Security.name == '') | 
        (Security.name == Security.ticker)
    ).all()
    
    logger.info(f"Found {len(securities)} securities with missing or default names")
    
    # Get API key
    api_key = os.getenv('ALPHA_VANTAGE_KEY')
    if not api_key:
        logger.error("No Alpha Vantage API key found in environment variables")
        return
    
    # Process each security
    success_count = 0
    error_count = 0
    
    for i, security in enumerate(securities):
        try:
            logger.info(f"Processing {i+1}/{len(securities)}: {security.ticker}")
            
            # Fetch company information
            company_info = fetch_company_info(security.ticker, api_key)
            
            if company_info and company_info.get('name'):
                # Update security with company information
                security.name = company_info.get('name')
                security.exchange = company_info.get('exchange', security.exchange)
                security.asset_type = company_info.get('asset_type', 'Equity')
                security.sector = company_info.get('sector', '')
                security.currency = company_info.get('currency', 'USD')
                security.updated_at = datetime.utcnow()
                
                # Also update or create SecurityMetadata
                metadata = SecurityMetadata.query.filter_by(ticker=security.ticker).first()
                if not metadata:
                    metadata = SecurityMetadata(ticker=security.ticker)
                    db.session.add(metadata)
                
                metadata.sector = company_info.get('sector', '')
                metadata.industry = company_info.get('industry', '')
                metadata.asset_type = company_info.get('asset_type', 'Equity')
                metadata.currency = company_info.get('currency', 'USD')
                metadata.exchange = company_info.get('exchange', '')
                metadata.last_updated = datetime.utcnow()
                
                # Commit changes
                db.session.commit()
                
                logger.info(f"Updated {security.ticker} with name: {security.name}")
                success_count += 1
            else:
                logger.warning(f"Could not get company information for {security.ticker}")
                error_count += 1
        
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing {security.ticker}: {str(e)}")
            db.session.rollback()
    
    logger.info(f"Completed processing {len(securities)} securities")
    logger.info(f"Success: {success_count}, Errors: {error_count}")

def main():
    """Main function"""
    app = create_app()
    with app.app_context():
        logger.info("Starting to fix missing company names...")
        fix_missing_names()
        logger.info("Completed fixing missing company names")

if __name__ == "__main__":
    main()