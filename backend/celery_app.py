import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery first without Flask integration
celery = Celery("quant_scope", broker=REDIS_URL, backend=REDIS_URL)

# Configure basic settings
celery.conf.update({
    'task_default_rate_limit': '75/m',
    'worker_prefetch_multiplier': 1,
    'worker_concurrency': 2,
    'worker_max_memory_per_child': 200000,
    'worker_max_tasks_per_child': 50,
    'broker_connection_retry_on_startup': True,
    'accept_content': ['json'],
    'task_serializer': 'json',
    'result_serializer': 'json',
    'task_default_queue': 'default',
    'task_routes': {
        'backend.tasks.*': {'queue': 'default'},
        'backend.services.*': {'queue': 'default'},
    },
    'task_annotations': {
        'backend.tasks.*': {'rate_limit': '75/m'}
    },
})

# Improved context handling
def configure_celery(app):
    # Update with app config
    celery.conf.update(app.config)
    
    # Set beat schedule inside configure function to have access to app config
    celery.conf.beat_schedule = {
        'update-prices-during-market': {
            'task': 'backend.services.price_update_service.update_prices',
            'schedule': crontab(minute='*/30', hour='9-16', day_of_week='1-5'),
            'options': {'expires': 290}
        },
        'save-closing-prices': {
            'task': 'backend.services.price_update_service.save_closing_prices',
            'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),
            'options': {'expires': 3600}
        },
        'update-historical-data': {
            'task': 'backend.tasks.backfill_historical_prices',
            'schedule': crontab(hour='*/1', minute=15),  # Run every hour at 15 minutes past
            'options': {'expires': 3000}
        },
        'update-prices-force': {
            'task': 'backend.services.price_update_service.force_update_all',
            'schedule': crontab(hour=20, minute=0),
            'options': {'expires': 7200}
        },
        'dev-backfill-historical-prices': {
            'task': 'backend.tasks.backfill_historical_prices',
            'kwargs': {'force_update': True},
            'schedule': crontab(minute='*/15'),  # Run every 15 minutes for testing
            'options': {'expires': 120}
        }
    }

    # Create a subclass of Task
    class ContextTask(celery.Task):
        abstract = True
        
        def __call__(self, *args, **kwargs):
            if not flask_app:
                raise RuntimeError("Flask app is not initialized")
            with flask_app.app_context():
                return super().__call__(*args, **kwargs)
    
    # Apply our custom task class as default
    celery.Task = ContextTask
    
    # Discover tasks after context is set up
    celery.autodiscover_tasks([
        'backend.tasks',
        'backend.services'
    ], force=True)
    
    return celery

# Ensure beat schedule directory exists
os.makedirs('/var/run/quantscope', exist_ok=True)