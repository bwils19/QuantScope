import os
from dotenv import load_dotenv

load_dotenv()

# Import the celery instance
from backend.celery_app import celery

from backend.services.price_update_service import scheduled_price_update, save_closing_prices

if __name__ == '__main__':
    celery.start()
