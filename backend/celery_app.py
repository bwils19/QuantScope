# backend/celery_app.py
import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery = Celery(
    "quant_scope",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery.autodiscover_tasks([
    'backend.tasks',
    'backend.services'], force=True)

# Base configuration
celery.conf.update({
    'task_default_rate_limit': '75/m',
    'worker_prefetch_multiplier': 1,
    'worker_concurrency': 2,
    'worker_max_memory_per_child': 200000,  # Restart worker after 200MB
    'worker_max_tasks_per_child': 50,
    'broker_connection_retry_on_startup': True,
    'accept_content': ['json'],
    'task_serializer': 'json',
    'result_serializer': 'json',
    'task_default_queue': 'default',

    # 'beat_scheduler': 'redbeat.RedBeatScheduler',
    # 'beat_schedule_filename': '/var/run/quantscope/celerybeat-schedule',
    'task_routes': {
        'backend.tasks.*': {'queue': 'default'},
        'backend.services.*': {'queue': 'default'},
    },
    'task_annotations': {
        'backend.tasks.*': {'rate_limit': '75/m'}
    },
    'beat_schedule': {
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
            'task': 'backend.services.price_update_service.update_historical_data',
            'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
            'options': {'expires': 7200}
        },
        'update-prices-force': {
            'task': 'backend.services.price_update_service.force_update_all',
            'schedule': crontab(hour=20, minute=0),
            'options': {'expires': 7200}
        },
        'dev-backfill-historical-prices': {
            'task': 'backend.tasks.backfill_historical_prices',
            'schedule': crontab(minute='*/2'),  # every 2 minutes just to test
            'options': {'expires': 120}
        }
    }
})

# Ensure beat schedule directory exists
os.makedirs('/var/run/quantscope', exist_ok=True)

def configure_celery(app):
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        abstract = True
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
    return celery

try:
    from backend.app import create_app
    flask_app = create_app()
    configure_celery(flask_app)
except Exception as e:
    print(f"WARNING: Could not configure Celery with Flask app context: {e}")

