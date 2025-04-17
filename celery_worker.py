import os
import sys
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('celery_worker')

logger.info("Starting celery worker initialization")

# Add the project directory to the Python path if needed
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import Flask app and create it
logger.info("Creating Flask app")
from backend.app import create_app
app = create_app()

# Import celery and configure it WITH the app context
logger.info("Configuring Celery with app context")
from backend.celery_app import celery, configure_celery
configure_celery(app)

# Explicitly register historical data task
@celery.task(name='historical.update_data', bind=True)
def update_historical_data(self, force_update=False):
    """Task to update historical data"""
    logger.info(f"Starting historical data update task with force={force_update}")
    
    from flask import current_app
    from backend.services.historical_data_service import HistoricalDataService
    
    try:
        # Log app context
        if not current_app:
            logger.error("No Flask app context!")
            return {"success": False, "error": "No Flask app context"}
            
        # Create service and perform update
        service = HistoricalDataService()
        result = service.update_historical_data(force_update=force_update)
        logger.info(f"Historical update completed with result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in update_historical_data task: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

# Make celery available for workers
logger.info("Celery worker initialization complete")