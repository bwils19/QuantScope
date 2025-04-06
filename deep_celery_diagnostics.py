#!/usr/bin/env python3
"""
Comprehensive Celery Diagnostics and Troubleshooting Script

This script provides in-depth analysis of Celery configuration, 
task registration, and potential startup issues.
"""
import os
import sys
import traceback
import logging
import subprocess

# Ensure project root is in Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

def configure_logging():
    """Configure comprehensive logging"""
    log_dir = '/var/log/quantscope'
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.path.join(log_dir, 'deep_celery_diagnostics.log'))
        ]
    )

def check_systemd_service_config():
    """
    Check systemd service configuration for Celery workers and beat
    """
    logging.info("=== Systemd Service Configuration ===")
    services = ['quantscope-worker.service', 'quantscope-beat.service']
    
    for service in services:
        logging.info(f"\nChecking {service}")
        try:
            # Get service status
            status_output = subprocess.check_output(
                ['systemctl', 'status', service], 
                stderr=subprocess.STDOUT, 
                universal_newlines=True
            )
            logging.info(status_output)
            
            # Get service configuration
            try:
                config_output = subprocess.check_output(
                    ['systemctl', 'cat', service], 
                    stderr=subprocess.STDOUT, 
                    universal_newlines=True
                )
                logging.info("Service Configuration:")
                logging.info(config_output)
            except subprocess.CalledProcessError as config_err:
                logging.error(f"Error getting service configuration: {config_err}")
        
        except subprocess.CalledProcessError as status_err:
            logging.error(f"Error checking {service} status: {status_err}")

def check_python_environment():
    """
    Detailed Python environment check
    """
    logging.info("=== Python Environment ===")
    
    # Python executable and version
    logging.info(f"Python Executable: {sys.executable}")
    logging.info(f"Python Version: {sys.version}")
    
    # Virtual environment
    logging.info(f"Virtual Env: {sys.prefix}")
    
    # Python path
    logging.info("Python Path:")
    for path in sys.path:
        logging.info(path)
    
    # Installed packages
    try:
        import pkg_resources
        logging.info("\n=== Installed Packages ===")
        for package in sorted(pkg_resources.working_set, key=lambda x: x.project_name):
            logging.info(f"{package.project_name}=={package.version}")
    except ImportError:
        logging.error("Could not import pkg_resources to list packages")

def check_celery_configuration():
    """
    Comprehensive Celery configuration check
    """
    logging.info("=== Celery Configuration Diagnostics ===")
    
    try:
        # Import Celery app
        from backend.app import create_app
        from backend.celery_app import celery
        
        # Create app context
        app = create_app()
        with app.app_context():
            # Detailed Celery configuration
            logging.info("Celery Configuration:")
            config_attrs = [
                'broker_url', 
                'result_backend', 
                'task_routes', 
                'task_annotations', 
                'beat_schedule'
            ]
            
            for attr in config_attrs:
                try:
                    value = getattr(celery.conf, attr, 'Not Set')
                    logging.info(f"{attr}: {value}")
                except Exception as attr_err:
                    logging.error(f"Error checking {attr}: {attr_err}")
            
            # List registered tasks
            logging.info("\n=== Registered Tasks ===")
            for task_name in sorted(celery.tasks.keys()):
                logging.info(task_name)
    
    except Exception as e:
        logging.error("Error in Celery configuration check:")
        logging.error(traceback.format_exc())

def check_redis_connection():
    """
    Detailed Redis connection diagnostics
    """
    logging.info("=== Redis Connection Diagnostics ===")
    
    try:
        import redis
        
        # Get Redis URL from environment or default
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        
        # Create Redis client
        r = redis.from_url(redis_url)
        
        # Comprehensive connection test
        logging.info(f"Redis URL: {redis_url}")
        logging.info(f"Ping Response: {r.ping()}")
        
        # Server information
        server_info = r.info()
        logging.info("\nRedis Server Information:")
        for key, value in server_info.items():
            if isinstance(value, (int, str, float)):
                logging.info(f"{key}: {value}")
    
    except Exception as e:
        logging.error("Redis connection diagnostics failed:")
        logging.error(traceback.format_exc())

def main():
    """Run comprehensive Celery diagnostics"""
    configure_logging()
    
    logging.info("=== Starting Deep Celery Diagnostics ===")
    
    # Run diagnostic checks
    check_systemd_service_config()
    check_python_environment()
    check_celery_configuration()
    check_redis_connection()
    
    logging.info("=== Deep Celery Diagnostics Complete ===")
    print("\nDiagnostics complete. Check the log file for detailed information.")
    print("Log file: /var/log/quantscope/deep_celery_diagnostics.log")

if __name__ == "__main__":
    main()