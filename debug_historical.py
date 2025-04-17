import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project directory to the Python path
sys.path.insert(0, '/root/QuantScope')

# Create the app and push context
from backend.app import create_app
app = create_app()
with app.app_context():
    # Import the service after app context is active
    from backend.services.historical_data_service import HistoricalDataService
    
    # Create service and test the get_tickers method directly
    service = HistoricalDataService()
    try:
        print(f"Testing get_tickers_needing_update at {datetime.now()}")
        tickers = service.get_tickers_needing_update()
        print(f"Found {len(tickers)} tickers that need updating: {tickers[:10]}")

        # Force update for a specific ticker to test
        print("\nTesting force update for AAPL")
        result = service.update_ticker_historical_data('AAPL', force_update=True) 
        print(f"Update result: {result}")
    except Exception as e:
        import traceback
        print(f"Error testing historical data service: {e}")
        traceback.print_exc()