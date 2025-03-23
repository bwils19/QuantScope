from backend.app import create_app
from backend import db
from sqlalchemy import inspect, MetaData, Table, Column, Integer, DateTime, String, Float, Date, ForeignKey, \
    UniqueConstraint
from datetime import datetime
import traceback

app = create_app()

with app.app_context():
    try:
        # Check for existing tables
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # Add Portfolio Securities junction table if it doesn't exist
        if 'portfolio_securities' not in existing_tables:
            print("\nCreating portfolio_securities junction table...")

            # Use raw SQL to create the table to avoid ORM issues
            db.session.execute(db.text("""
            CREATE TABLE portfolio_securities (
                id SERIAL PRIMARY KEY,
                portfolio_id INTEGER NOT NULL REFERENCES portfolios(id),
                security_id INTEGER NOT NULL REFERENCES securities(id),
                amount_owned FLOAT NOT NULL,
                purchase_price FLOAT,
                purchase_date DATE,
                total_value FLOAT,
                value_change FLOAT,
                value_change_pct FLOAT,
                total_gain FLOAT,
                total_gain_pct FLOAT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uix_portfolio_security UNIQUE (portfolio_id, security_id)
            )
            """))

            db.session.commit()
            print("Portfolio securities junction table created successfully.")

            # Migrate existing data
            print("\nMigrating existing securities data to junction table...")
            db.session.execute(db.text("""
            INSERT INTO portfolio_securities (
                portfolio_id, 
                security_id, 
                amount_owned,
                purchase_price,
                purchase_date,
                total_value,
                value_change,
                value_change_pct,
                total_gain,
                total_gain_pct,
                added_at,
                updated_at
            )
            SELECT 
                portfolio_id,
                id AS security_id,
                amount_owned,
                purchase_price,
                purchase_date,
                total_value,
                value_change,
                value_change_pct,
                total_gain,
                total_gain_pct,
                added_at,
                updated_at
            FROM securities
            """))

            db.session.commit()
            print("Data migration completed successfully.")

            # Verify the table and migration
            result = db.session.execute(
                db.text("SELECT COUNT(*) AS junction_count FROM portfolio_securities")).fetchone()
            junction_count = result[0]

            security_count = db.session.execute(db.text("SELECT COUNT(*) FROM securities")).fetchone()[0]

            print(f"\nVerification: {junction_count} records in junction table")
            print(f"Original securities count: {security_count}")
            print(f"Migration {'successful' if junction_count == security_count else 'incomplete'}")

            print("\nVerifying portfolio_securities table columns:")
            junction_columns = inspector.get_columns('portfolio_securities')
            for column in junction_columns:
                print(f"  - {column['name']}: {column['type']}")

        else:
            print("\nPortfolio securities junction table already exists.")

    except Exception as e:
        print(f"Error during migration: {str(e)}")
        print(traceback.format_exc())
        db.session.rollback()