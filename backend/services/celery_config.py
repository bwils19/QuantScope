from celery import Celery

def make_celery(app):
    """
    Configure Celery using the Flask app context.
    """

    celery = Celery(
        app.import_name,
        broker="redis://localhost:6379/0",
        backend="redis://localhost:6379/0",
        include=["backend.services.price_update_service"],
    )

    celery.conf.update(app.config)
    return celery
