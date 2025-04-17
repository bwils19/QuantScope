import os
import sys
import logging
from backend.app import create_app
from backend.celery_app import celery, configure_celery

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('celery_worker')
logger.info("Starting celery worker initialization")

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create Flask app and configure celery context
app = create_app()
configure_celery(app)
logger.info("Flask app created and Celery configured")

# This import MUST come after the app context is set up
from backend.tasks import backfill_historical_prices

logger.info("Celery worker initialization complete")
