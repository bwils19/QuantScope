# celery_worker.py

import os
import sys
import logging

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("celery_worker")

logger.info("Starting celery worker initialization")

from backend.app import create_app
from backend.celery_app import celery, configure_celery

flask_app = create_app()
configure_celery(flask_app)

logger.info("Flask app created and Celery configured")

# Import the tasks explicitly to ensure they're registered
from backend.tasks import backfill_historical_prices

logger.info("Celery worker initialization complete")
