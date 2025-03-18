from celery import Celery

# Create the base celery instance
celery = Celery(
    "quant_scope",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)


def configure_celery(app):
    # Update celery config with any relevant Flask config
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask

    return celery