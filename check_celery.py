#!/usr/bin/env python3
"""
Script to check if Celery is running correctly.
This script sends a simple task to Celery and checks if it's executed.
"""
import os
import sys
import time
from datetime import datetime

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print(f"Checking Celery status at {datetime.now()}")
    
    # Import after parsing args to avoid slow imports if help is requested
    from backend.app import create_app
    from backend.celery_app import celery
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        # Check if Redis URL is set
        redis_url = os.getenv('REDIS_URL')
        if not redis_url:
            print("ERROR: REDIS_URL environment variable is not set.")
            print("Please set it in your .env file or environment.")
            return
        
        print(f"Redis URL: {redis_url}")
        
        # Try to connect to Redis
        try:
            import redis
            r = redis.from_url(redis_url)
            r.ping()
            print("Successfully connected to Redis.")
        except Exception as e:
            print(f"ERROR: Could not connect to Redis: {str(e)}")
            print("Please check your Redis configuration.")
            return
        
        # Create a simple task
        @celery.task(name='check_celery.test_task')
        def test_task():
            return {'status': 'ok', 'timestamp': datetime.now().isoformat()}
        
        # Send the task
        print("Sending test task to Celery...")
        try:
            result = test_task.delay()
            print(f"Task ID: {result.id}")
            
            # Wait for the result
            print("Waiting for task result...")
            for i in range(10):
                if result.ready():
                    break
                print(".", end="", flush=True)
                time.sleep(1)
            print()
            
            if result.ready():
                print("Task completed!")
                print(f"Result: {result.get()}")
                print("Celery is working correctly.")
            else:
                print("Task did not complete within 10 seconds.")
                print("This could mean:")
                print("1. Celery worker is not running")
                print("2. Celery worker is running but not processing tasks")
                print("3. Celery worker is running but taking too long to process tasks")
                print("\nCheck the Celery worker logs for more information:")
                print("sudo tail -f /var/log/celery/worker.log")
        except Exception as e:
            print(f"ERROR: Could not send task to Celery: {str(e)}")
            print("This could mean:")
            print("1. Celery is not configured correctly")
            print("2. Redis is not accessible")
            print("3. There's an issue with the Celery configuration")
            print("\nCheck your Celery and Redis configuration.")

if __name__ == "__main__":
    main()