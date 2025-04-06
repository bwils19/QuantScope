#!/usr/bin/env python3
"""
Comprehensive Celery Diagnostics Script

This script helps diagnose issues with Celery worker and beat service initialization.
"""
import os
import sys
import traceback
import logging

# Ensure project root is in Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def configure_logging():
    """Configure logging for diagnostics"""
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/quantscope/celery_diagnostics.log')
        ]
    )

def check_environment():
    """Check Python and environment configuration"""
    logging.info("=== Environment Check ===")
    logging.info(f"Python Version: {sys.version}")
    logging.info(f"Python Executable: {sys.executable}")
    logging.info(f"Python Path: {sys.path}")
    
    # Check important environment variables
    env_vars = [
        'REDIS_URL', 
        'CELERY_BROKER_URL', 
        'CELERY_RESULT_BACKEND', 
        'FLASK_ENV', 
        'PYTHONPATH'
    ]
    
    for var in env_vars:
        logging.info(f"{var}: {os.environ.get(var, 'Not Set')}")

def test_celery_import():
    """Test Celery import and basic configuration"""
    logging.info("=== Celery Import Test ===")
    try:
        import celery
        logging.info(f"Celery Version: {celery.__version__}")
        
        # Import Celery app
        from backend.celery_app import celery as app
        logging.info("Celery app successfully imported")
        
        # Check broker configuration
        logging.info(f"Broker URL: {app.conf.broker_url}")
        logging.info(f"Result Backend: {app.conf.result_backend}")
    
    except ImportError as e:
        logging.error("Failed to import Celery")
        logging.error(traceback.format_exc())
    except Exception as e:
        logging.error("Error in Celery configuration")
        logging.error(traceback.format_exc())

def test_task_registration():
    """Test task registration and discovery"""
    logging.info("=== Task Registration Test ===")
    try:
        from backend.celery_app import celery as app
        
        # List registered tasks
        logging.info("Registered Tasks:")
        for task in sorted(app.tasks.keys()):
            logging.info(task)
    
    except Exception as e:
        logging.error("Failed to list registered tasks")
        logging.error(traceback.format_exc())

def test_redis_connection():
    """Test Redis connection"""
    logging.info("=== Redis Connection Test ===")
    try:
        import redis
        
        # Get Redis URL from environment or default
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Test connection
        r.ping()
        logging.info("Redis connection successful")
    
    except Exception as e:
        logging.error("Redis connection failed")
        logging.error(traceback.format_exc())

def test_beat_schedule():
    """Test beat schedule configuration"""
    logging.info("=== Beat Schedule Test ===")
    try:
        from backend.celery_app import celery as app
        
        logging.info("Beat Schedule Configuration:")
        for name, task_info in app.conf.beat_schedule.items():
            logging.info(f"Task: {name}")
            logging.info(f"  Scheduled Task: {task_info.get('task', 'N/A')}")
            logging.info(f"  Schedule: {task_info.get('schedule', 'N/A')}")
            logging.info(f"  Options: {task_info.get('options', 'N/A')}")
    
    except Exception as e:
        logging.error("Failed to retrieve beat schedule")
        logging.error(traceback.format_exc())

def main():
    """Run all diagnostic checks"""
    configure_logging()
    
    logging.info("=== Starting Celery Diagnostics ===")
    
    check_environment()
    test_celery_import()
    test_task_registration()
    test_redis_connection()
    test_beat_schedule()
    
    logging.info("=== Celery Diagnostics Complete ===")

if __name__ == "__main__":
    main()