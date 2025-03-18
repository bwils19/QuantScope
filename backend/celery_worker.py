from backend.app import app
from backend.services.celery_config import make_celery

celery = make_celery(app)
