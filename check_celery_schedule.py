#!/usr/bin/env python3
"""
Script to check the Celery beat schedule and verify that tasks are scheduled correctly.
"""
import os
import sys
from datetime import datetime, timedelta

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    print(f"Checking Celery beat schedule at {datetime.now()}")
    
    # Import after parsing args to avoid slow imports if help is requested
    from backend.app import create_app
    from backend.celery_app import celery
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        # Get the beat schedule
        schedule = celery.conf.beat_schedule
        
        print("\nScheduled Tasks:")
        print("=" * 80)
        
        for task_name, task_info in schedule.items():
            print(f"Task: {task_name}")
            print(f"  Function: {task_info['task']}")
            
            # Get the schedule
            schedule_obj = task_info['schedule']
            if hasattr(schedule_obj, 'run_every'):
                # For interval schedules
                print(f"  Schedule: Every {schedule_obj.run_every} seconds")
                next_run = datetime.now() + timedelta(seconds=schedule_obj.run_every)
                print(f"  Next run: {next_run}")
            elif hasattr(schedule_obj, 'minute'):
                # For crontab schedules
                minute = schedule_obj.minute
                hour = schedule_obj.hour
                day_of_week = schedule_obj.day_of_week
                
                print(f"  Schedule: crontab(minute='{minute}', hour='{hour}', day_of_week='{day_of_week}')")
                
                # Try to calculate the next run time
                if isinstance(minute, str) and '*' in minute:
                    print("  Next run: Every minute in the specified hours and days")
                else:
                    print("  Next run: At the specified times")
            else:
                print(f"  Schedule: {schedule_obj}")
            
            # Get the options
            if 'options' in task_info:
                print(f"  Options: {task_info['options']}")
            
            print("-" * 80)
        
        # Check if the Celery worker is running
        try:
            # Try to ping the Celery worker
            response = celery.control.ping(timeout=1.0)
            if response:
                print("\nCelery worker is running.")
                print(f"Response: {response}")
            else:
                print("\nCelery worker is not responding.")
        except Exception as e:
            print(f"\nError checking Celery worker: {str(e)}")
            print("Make sure the Celery worker is running.")
        
        # Check if the Celery beat is running
        try:
            import psutil
            beat_running = False
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if proc.info['cmdline'] and 'celery' in ' '.join(proc.info['cmdline']) and 'beat' in ' '.join(proc.info['cmdline']):
                    beat_running = True
                    print(f"\nCelery beat is running (PID: {proc.info['pid']}).")
                    break
            
            if not beat_running:
                print("\nCelery beat does not appear to be running.")
        except ImportError:
            print("\nCould not check if Celery beat is running (psutil not installed).")
            print("Install psutil with: pip install psutil")
        except Exception as e:
            print(f"\nError checking Celery beat: {str(e)}")
        
        print("\nTo manually trigger a task, run:")
        print("python -c \"from backend.app import create_app; from backend.services.price_update_service import force_update_all; app = create_app(); with app.app_context(): force_update_all()\"")

if __name__ == "__main__":
    main()