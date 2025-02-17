
from backend.app import create_app
from backend import db
from backend.models import Security, SecurityMetadata
from backend.services.market.api_client import AlphaVantageClient
import time

import os
from dotenv import load_dotenv

load_dotenv()
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_KEY')
print(f"API Key loaded: {'Yes' if ALPHA_VANTAGE_API_KEY else 'No'}")

app = create_app()


def populate_metadata():
    with app.app_context():
        api_client = AlphaVantageClient(ALPHA_VANTAGE_API_KEY)

        # Get unique tickers from securities table
        unique_tickers = db.session.query(Security.ticker).distinct().all()
        tickers = [t[0] for t in unique_tickers]

        print(f"Found {len(tickers)} unique tickers to process")

        for ticker in tickers:
            try:
                # Check if we already have metadata for this ticker
                existing = SecurityMetadata.query.filter_by(ticker=ticker).first()
                if existing:
                    print(f"Metadata already exists for {ticker}, skipping...")
                    continue

                print(f"Fetching metadata for {ticker}...")
                overview_data = api_client.fetch_security_overview(ticker)

                if overview_data:
                    metadata = SecurityMetadata(**overview_data)
                    db.session.add(metadata)
                    db.session.commit()
                    print(f"Added metadata for {ticker}")
                else:
                    print(f"No metadata available for {ticker}")

                time.sleep(0.1)  # should be able to do it this quick

            except Exception as e:
                print(f"Error processing {ticker}: {str(e)}")
                db.session.rollback()
                continue


if __name__ == "__main__":
    populate_metadata()
