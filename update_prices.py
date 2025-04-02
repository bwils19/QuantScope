#!/usr/bin/env python3
"""
Script to manually trigger price updates and historical data updates.
This is useful for testing and for manually updating prices if needed.
"""
import os
import sys
import argparse
from datetime import datetime

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description='Manually trigger price updates')
    parser.add_argument('--task', choices=['prices', 'closing', 'historical', 'all'], 
                        default='all', help='Which task to run')
    parser.add_argument('--force', action='store_true', 
                        help='Force update even if market is closed')
    args = parser.parse_args()
    
    print(f"Starting manual update at {datetime.now()}")
    
    # Import after parsing args to avoid slow imports if help is requested
    from backend.app import create_app
    from backend.services.price_update_service import (
        PriceUpdateService, 
        scheduled_price_update,
        save_closing_prices,
        update_historical_data
    )
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        if args.task in ['prices', 'all']:
            print("Running price update task...")
            if args.force:
                # Run directly without market open check
                service = PriceUpdateService()
                result = service.update_all_portfolio_prices()
                print(f"Price update result: {result}")
            else:
                # Use the Celery task
                result = scheduled_price_update()
                print(f"Price update task result: {result}")
        
        if args.task in ['closing', 'all']:
            print("Running closing prices task...")
            result = save_closing_prices()
            print(f"Closing prices task result: {result}")
        
        if args.task in ['historical', 'all']:
            print("Running historical data update task...")
            result = update_historical_data()
            print(f"Historical data update result: {result}")
    
    print(f"Update completed at {datetime.now()}")

if __name__ == "__main__":
    main()