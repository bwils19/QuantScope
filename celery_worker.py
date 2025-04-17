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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import celery first
from backend.celery_app import celery

class FlaskTask(celery.Task):
    abstract = True
    
    def __call__(self, *args, **kwargs):
        logger.info(f"Executing task: {self.name}")
        return super().__call__(*args, **kwargs)

celery.Task = FlaskTask


@celery.task(name='test.ping')
def ping():
    """Simple task to test worker functionality"""
    logger.info("Ping task executed")
    return {"status": "ok", "message": "Worker is functioning properly"}

logger.info("Celery worker initialization complete")