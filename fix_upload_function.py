#!/usr/bin/env python3
"""
Script to modify the create_portfolio_from_file function to properly set previous_close values.
This ensures that newly uploaded portfolios will have accurate DAY CHANGE metrics.
"""

import logging
import os
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import after environment variables are loaded
from backend import db
from backend.app import create_app  # Correct import for create_app

def patch_create_portfolio_from_file():
    """
    Apply a patch to the create_portfolio_from_file function to properly set previous_close values.
    
    This function doesn't actually modify the source code, but demonstrates the changes
    that should be made to the function in auth_routes.py.
    """
    logger.info("This script demonstrates the changes needed in auth_routes.py")
    logger.info("Please manually apply these changes to the create_portfolio_from_file function:")
    
    print("\n" + "="*80)
    print("CHANGES TO MAKE IN backend/routes/auth_routes.py:")
    print("="*80)
    
    print("""
In the create_portfolio_from_file function (around line 1244-1256), replace:

```python
# Check StockCache for current price
cache = StockCache.query.filter_by(ticker=ticker).first()
if cache and cache.data:
    current_price = cache.data.get('currentPrice', 0)
    securities_with_prices += 1

# If no price, use purchase price as fallback
if current_price == 0 and purchase_price > 0:
    current_price = purchase_price

# Update security price if there is one
if current_price > 0:
    security.current_price = current_price
```

With:

```python
# Check StockCache for current price and previous close
cache = StockCache.query.filter_by(ticker=ticker).first()
if cache and cache.data:
    current_price = cache.data.get('currentPrice', 0)
    previous_close = cache.data.get('previousClose', current_price)
    securities_with_prices += 1
    
    # Update security price if there is one
    if current_price > 0:
        security.current_price = current_price
        security.previous_close = previous_close
else:
    # If no cache data, try to get from historical data
    historical_data = db.session.query(SecurityHistoricalData) \\
        .filter(SecurityHistoricalData.ticker == ticker) \\
        .order_by(SecurityHistoricalData.date.desc()) \\
        .limit(2) \\
        .all()
    
    if len(historical_data) >= 2:
        # Use the most recent day for current_price and the day before for previous_close
        current_price = historical_data[0].close_price
        previous_close = historical_data[1].close_price
        
        # Update the security
        security.current_price = current_price
        security.previous_close = previous_close
    elif len(historical_data) == 1:
        # If only one day of data, use it for both
        current_price = historical_data[0].close_price
        previous_close = current_price
        
        security.current_price = current_price
        security.previous_close = previous_close
    elif purchase_price > 0:
        # If no historical data but we have purchase price, use it
        current_price = purchase_price
        previous_close = purchase_price
        
        security.current_price = current_price
        security.previous_close = previous_close
```

This change ensures that both current_price and previous_close are properly set when creating securities from uploaded files.
    """)
    
    print("="*80)
    logger.info("After making these changes, newly uploaded portfolios will have accurate DAY CHANGE metrics.")

def main():
    """Main function"""
    app = create_app()
    with app.app_context():
        patch_create_portfolio_from_file()

if __name__ == "__main__":
    main()