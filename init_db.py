from backend.app import create_app
from backend import db
from backend.models import User, Security, Portfolio, SecurityHistoricalData
from sqlalchemy import inspect, text, MetaData, Table, Column, Integer, DateTime, String, Text
from backend.services.historical_data_service import HistoricalDataService
from datetime import datetime
import asyncio
import time

app = create_app()

with app.app_context():
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
    print("Actual Database Path:", db.engine.url)

    # Check for existing tables
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    # Check for and/or create historical data update log table
    if 'historical_data_update_log' not in existing_tables:
        print("\nCreating historical data update log table...")
        metadata = MetaData()

        # Define the table
        historical_data_update_log = Table(
            'historical_data_update_log',
            metadata,
            Column('id', Integer, primary_key=True),
            Column('update_time', DateTime, default=datetime.utcnow),
            Column('tickers_updated', Integer),
            Column('records_added', Integer),
            Column('status', String(50)),
            Column('error', Text, nullable=True)
        )

        # Create only this table
        historical_data_update_log.create(db.engine)
        print("Historical data update log table created.")
    else:
        print("\nHistorical data update log table already exists.")

    # Verify log table schema
    print("\nVerifying historical data update log table columns:")
    log_columns = inspector.get_columns('historical_data_update_log')
    for column in log_columns:
        print(f"  - {column['name']}: {column['type']}")

    # Your existing code continues here...
    if 'security_historical_data' not in existing_tables:
        print("\nCreating historical data table...")
        SecurityHistoricalData.__table__.create(db.engine)
        print("Historical data table created.")
    else:
        print("\nHistorical data table already exists.")
