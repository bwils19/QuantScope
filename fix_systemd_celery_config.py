#!/usr/bin/env python3
"""
Script to fix Celery systemd service configuration
"""
import os
import re

def update_systemd_service_files():
    """
    Update systemd service files for Celery worker and beat
    """
    services = {
        'quantscope-worker.service': {
            'path': '/etc/systemd/system/quantscope-worker.service',
            'old_import': r'celery -A backend\.celery_app:celery',
            'new_import': 'celery -A backend.celery_app:celery'
        },
        'quantscope-beat.service': {
            'path': '/etc/systemd/system/quantscope-beat.service',
            'old_import': r'celery -A backend\.celery_worker:celery',
            'new_import': 'celery -A backend.celery_app:celery'
        }
    }

    for service_name, config in services.items():
        try:
            # Read the service file
            with open(config['path'], 'r') as f:
                content = f.read()
            
            # Replace the Celery import
            updated_content = re.sub(
                r'ExecStart=.*celery.*',
                f'ExecStart=/root/QuantScope/venv/bin/{config["new_import"]} worker --loglevel=info --concurrency=2 --logfile=/var/log/celery/worker.log' 
                    if 'worker' in service_name else 
                f'ExecStart=/root/QuantScope/venv/bin/{config["new_import"]} beat --loglevel=info --logfile=/var/log/celery/beat.log',
                content
            )
            
            # Write the updated content back
            with open(config['path'], 'w') as f:
                f.write(updated_content)
            
            print(f"Updated {service_name} configuration")
        
        except Exception as e:
            print(f"Error updating {service_name}: {e}")

def reload_systemd_daemon():
    """
    Reload systemd daemon to recognize changes
    """
    try:
        import subprocess
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        print("Systemd daemon reloaded successfully")
    except Exception as e:
        print(f"Error reloading systemd daemon: {e}")

def main():
    print("Starting Celery Systemd Configuration Fix...")
    
    # Update service files
    update_systemd_service_files()
    
    # Reload systemd daemon
    reload_systemd_daemon()
    
    print("\nUpdate complete. Recommended next steps:")
    print("1. Restart Celery workers: sudo systemctl restart quantscope-worker.service")
    print("2. Restart Celery beat: sudo systemctl restart quantscope-beat.service")

if __name__ == "__main__":
    main()