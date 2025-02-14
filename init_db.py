from backend.app import create_app
from backend import db
from backend.models import User, Security, Portfolio, SecurityHistoricalData
from sqlalchemy import inspect, text
from backend.services.historical_data_service import HistoricalDataService
import asyncio
import time

app = create_app()

with app.app_context():
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
    print("Actual Database Path:", db.engine.url)

    # Check if historical data table exists
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    if 'security_historical_data' not in existing_tables:
        print("\nCreating historical data table...")
        # Create the new historical data table
        SecurityHistoricalData.__table__.create(db.engine)
        print("Historical data table created.")
    else:
        print("\nHistorical data table already exists.")

    # Verify historical data table schema
    print("\nVerifying historical data table columns:")
    columns = inspector.get_columns('security_historical_data')
    for column in columns:
        print(f"  - {column['name']}: {column['type']}")

    # Initialize historical data
    print("\nInitializing historical data...")
    service = HistoricalDataService()

    # Get unique tickers
    tickers = Security.query.with_entities(Security.ticker).distinct().all()
    tickers = [t[0] for t in tickers]

    print(f"Found {len(tickers)} unique tickers to process")

    # Check which tickers already have data
    existing_tickers = db.session.query(
        SecurityHistoricalData.ticker
    ).distinct().all()
    existing_tickers = set(t[0] for t in existing_tickers)

    # Filter for tickers that need data
    new_tickers = [t for t in tickers if t not in existing_tickers]
    print(f"Found {len(new_tickers)} tickers needing historical data")

    # Process each new ticker
    for i, ticker in enumerate(new_tickers, 1):
        try:
            print(f"Processing {ticker} ({i}/{len(new_tickers)})...")
            asyncio.run(service.update_historical_data())
            print(f"Successfully processed {ticker}")

            # Alpha Vantage rate limiting - i don't think this is necessary but gonna do it anyway
            if i < len(new_tickers):  # Don't wait after the last ticker
                print("Waiting 3 seconds for API rate limit...")
                time.sleep(3)

        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    print("\nHistorical data initialization complete!")

    # Verify data
    counts = db.session.query(
        SecurityHistoricalData.ticker,
        db.func.count(SecurityHistoricalData.id)
    ).group_by(SecurityHistoricalData.ticker).all()

    print("\nData counts by ticker:")
    for ticker, count in counts:
        print(f"  {ticker}: {count} records")

    # check for any tickers missing data
    missing_data = [t for t in tickers if t not in {c[0] for c in counts}]
    if missing_data:
        print("\nTickers missing historical data:")
        for ticker in missing_data:
            print(f"  - {ticker}")
