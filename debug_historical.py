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
    
    # Create service and check available methods
    service = HistoricalDataService()
    print("\nAvailable methods on HistoricalDataService:")
    print([method for method in dir(service) if not method.startswith('_')])
    
    # Test the update_historical_data method
    try:
        print("\nTesting update_historical_data method:")
        result = service.update_historical_data(force_update=True)
        print(f"Update result: {result}")
    except Exception as e:
        import traceback
        print(f"Error updating historical data: {e}")
        traceback.print_exc()
        
    # Check the market utils
    try:
        print("\nExamining MarketUtils:")
        market_utils = getattr(service, 'market_utils', None)
        if market_utils:
            print("Available methods on MarketUtils:")
            print([method for method in dir(market_utils) if not method.startswith('_')])
            
            # Try a method that should work
            print("\nTesting should_fetch_market_data:")
            result, reason = market_utils.should_fetch_market_data()
            print(f"Should fetch? {result}, Reason: {reason}")
    except Exception as e:
        print(f"Error examining MarketUtils: {e}")