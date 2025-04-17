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

# Import celery first
from backend.celery_app import celery

# Explicitly import tasks to ensure they're registered
logger.info("Importing tasks...")
from backend.tasks import backfill_historical_prices  # This is crucial to register the task

# Define what a celery worker needs
class FlaskTask(celery.Task):
    abstract = True
    
    def __call__(self, *args, **kwargs):
        logger.info(f"Executing task: {self.name}")
        return super().__call__(*args, **kwargs)

celery.Task = FlaskTask

# Add a simple test task to verify functionality
@celery.task(name='test.ping')
def ping():
    """Simple task to test worker functionality"""
    logger.info("Ping task executed")
    return {"status": "ok", "message": "Worker is functioning properly"}

logger.info("Celery worker initialization complete")