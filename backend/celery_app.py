from celery import Celery
from celery.schedules import crontab

# Create the base celery instance
celery = Celery(
    "quant_scope",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)


celery.conf.update(
    broker_connection_retry_on_startup=True,
    beat_schedule={
        'update-prices-every-5-min': {
            'task': 'backend.services.price_update_service.scheduled_price_update',
            'schedule': 300.0,  # every 5 minutes
            'options': {'expires': 290}
        },
        'save-closing-prices': {
            'task': 'backend.services.price_update_service.save_closing_prices',
            'schedule': crontab(hour=16, minute=0),  # 4:00 PM (market close)
            'options': {'expires': 3600}  # Tasks expire after 1 hour
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
