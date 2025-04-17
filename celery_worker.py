import os
import sys
import logging

# Set up logging
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

# Explicitly push app context for debug info
with app.app_context():
    from flask import current_app
    logger.info(f"App context started, app name: {current_app.name}")
    
    # Test DB connection to ensure it's working
    from backend import db
    try:
        db.session.execute("SELECT 1")
        db.session.commit()
        logger.info("Database connection test successful")
    except Exception as e:
        logger.error(f"Database connection error: {e}")

# Define a simple test task
@celery.task(name='test.app_context')
def test_app_context():
    from flask import current_app
    from backend import db
    
    try:
        # Check if we have app context
        if current_app:
            return {"success": True, "app_name": current_app.name}
        else:
            return {"success": False, "error": "No app context"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Make celery available for workers
logger.info("Celery worker initialization complete")