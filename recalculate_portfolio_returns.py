#!/usr/bin/env python3
"""
Script to recalculate total return for all portfolios.
This script will update the total_return and total_return_pct fields for all portfolios.
"""
import os
import sys
from datetime import datetime

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print(f"Starting portfolio return recalculation at {datetime.now()}")
    
    # Import after parsing args to avoid slow imports if help is requested
    from backend.app import create_app
    from backend.services.price_update_service import PriceUpdateService
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        service = PriceUpdateService()
        
        # Recalculate metrics for all portfolios
        result = service.recalculate_all_portfolio_metrics()
        
        if result.get('success', False):
            print(f"Successfully recalculated metrics for {result.get('success_count', 0)} portfolios")
            if result.get('error_count', 0) > 0:
                print(f"Failed to recalculate metrics for {result.get('error_count', 0)} portfolios")
        else:
            print(f"Failed to recalculate portfolio metrics: {result.get('error', 'Unknown error')}")
    
    print(f"Portfolio return recalculation completed at {datetime.now()}")

if __name__ == "__main__":
    main()