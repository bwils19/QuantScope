from backend.app import create_app
from backend.celery_app import celery, configure_celery

app = create_app()
configure_celery(app)
