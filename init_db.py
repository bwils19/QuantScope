from backend.app import create_app
from backend import db
from sqlalchemy import inspect, MetaData, Table, Column, Integer, DateTime, String, JSON, ForeignKey
from datetime import datetime

app = create_app()

with app.app_context():
    # Check for existing tables
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    # Add Risk Analysis Cache table if it doesn't exist
    if 'risk_analysis_cache' not in existing_tables:
        print("\nCreating risk analysis cache table...")
        metadata = MetaData()

        risk_cache_table = Table(
            'risk_analysis_cache',
            metadata,
            Column('id', Integer, primary_key=True),
            Column('portfolio_id', Integer, ForeignKey('portfolios.id'), unique=True),
            Column('cache_data', JSON),
            Column('created_at', DateTime, default=datetime.utcnow),
            Column('expires_at', DateTime)
        )

        risk_cache_table.create(db.engine)
        print("Risk analysis cache table created successfully.")

        print("\nVerifying risk analysis cache table columns:")
        risk_cache_columns = inspector.get_columns('risk_analysis_cache')
        for column in risk_cache_columns:
            print(f"  - {column['name']}: {column['type']}")
    else:
        print("\nRisk analysis cache table already exists.")