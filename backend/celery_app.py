from celery import Celery
from celery.schedules import crontab

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Redis URL from environment or use default
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create the base celery instance
celery = Celery(
    "quant_scope",
    broker=REDIS_URL,
    backend=REDIS_URL
)


celery.conf.task_default_rate_limit = '75/m'
celery.conf.worker_prefetch_multiplier = 1
celery.conf.worker_concurrency = 2

# Add memory optimization to prevent OOM kills
celery.conf.worker_max_memory_per_child = 200000  # Restart worker after using 200MB
celery.conf.worker_max_tasks_per_child = 50  # Restart after processing 50 tasks

celery.conf.update(
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # Regular price updates during market hours only
        'update-prices-during-market': {
            'task': 'backend.services.price_update_service.scheduled_price_update',
            'schedule': crontab(minute='*/30', hour='9-16', day_of_week='1-5'),  # Every 30 min during market hours
            'options': {'expires': 290}
        },
        # Closing prices at market close
        'save-closing-prices': {
            'task': 'backend.services.price_update_service.save_closing_prices',
            'schedule': crontab(hour=16, minute=0, day_of_week='1-5'),  # 4:00 PM (market close)
            'options': {'expires': 3600}  # Tasks expire after 1 hour
        },
        # Add new task to update historical data after market close
        'update-historical-data': {
            'task': 'backend.services.price_update_service.update_historical_data',
            'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),  # 4:30 PM (after market close)
            'options': {'expires': 7200}  # Tasks expire after 2 hours
        }
    }
)


def configure_celery(app):
    celery.conf.update(app.config)

    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super(ContextTask, self).__call__(*args, **kwargs)

    celery.conf.update(task_base=ContextTask)

    return celery
