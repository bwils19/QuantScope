from backend.app import create_app
from backend import db
from sqlalchemy import inspect, MetaData, Table, Column, Integer, DateTime, String, Float, Date, ForeignKey, \
    UniqueConstraint
from datetime import datetime
import traceback

app = create_app()


def create_portfolio_securities_table():
    with app.app_context():
        # Check for existing tables
        inspector = inspect(db.engine)
        existing_tables = inspector.get_table_names()

        # Add Portfolio Securities junction table if it doesn't exist
        if 'portfolio_securities' not in existing_tables:
            print("\nCreating portfolio_securities junction table...")
            metadata = MetaData()

            portfolio_securities_table = Table(
                'portfolio_securities',
                metadata,
                Column('id', Integer, primary_key=True),
                Column('portfolio_id', Integer, ForeignKey('portfolios.id'), nullable=False),
                Column('security_id', Integer, ForeignKey('securities.id'), nullable=False),
                Column('amount_owned', Float, nullable=False),
                Column('purchase_price', Float),
                Column('purchase_date', Date),
                Column('total_value', Float),
                Column('value_change', Float),
                Column('value_change_pct', Float),
                Column('total_gain', Float),
                Column('total_gain_pct', Float),
                Column('added_at', DateTime, default=datetime.utcnow),
                Column('updated_at', DateTime, default=datetime.utcnow, onupdate=datetime.utcnow),
                UniqueConstraint('portfolio_id', 'security_id', name='uix_portfolio_security')
            )

            try:
                portfolio_securities_table.create(db.engine)
                print("Portfolio securities junction table created successfully.")

                # Migrate existing data
                print("\nMigrating existing securities data to junction table...")
                conn = db.engine.connect()

                # Insert data into junction table
                conn.execute(db.text("""
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

                print("Data migration completed successfully.")

                # Verify the table and migration
                verification_query = db.text("""
                SELECT COUNT(*) AS junction_count FROM portfolio_securities;
                """)
                result = conn.execute(verification_query).fetchone()
                junction_count = result[0]

                security_count_query = db.text("""
                SELECT COUNT(*) FROM securities;
                """)
                security_count = conn.execute(security_count_query).fetchone()[0]

                print(f"\nVerification: {junction_count} records in junction table")
                print(f"Original securities count: {security_count}")
                print(f"Migration {'successful' if junction_count == security_count else 'incomplete'}")

                print("\nVerifying portfolio_securities table columns:")
                junction_columns = inspector.get_columns('portfolio_securities')
                for column in junction_columns:
                    print(f"  - {column['name']}: {column['type']}")

            except Exception as e:
                print(f"Error creating portfolio_securities table: {str(e)}")
                print(traceback.format_exc())
                return False

            return True
        else:
            print("\nPortfolio securities junction table already exists.")
            return True


def update_securities_structure():
    """
    Create a new securities table with unique ticker constraint
    and without portfolio-specific columns
    """
    with app.app_context():
        inspector = inspect(db.engine)

        # Check if temporary table already exists
        if 'securities_new' in inspector.get_table_names():
            print("Cleaning up previous migration attempt...")
            db.engine.execute("DROP TABLE IF EXISTS securities_new")

        try:
            print("\nCreating new securities table structure...")
            # First, create a new securities table without portfolio-specific fields
            db.engine.execute("""
            CREATE TABLE securities_new (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(20) NOT NULL,
                name VARCHAR(200) NOT NULL,
                exchange VARCHAR(50),
                asset_type VARCHAR(50) DEFAULT 'Equity',
                sector VARCHAR(50),
                currency VARCHAR(3) DEFAULT 'USD',
                current_price FLOAT,
                previous_close FLOAT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # Add unique constraint on ticker
            db.engine.execute("CREATE UNIQUE INDEX uix_securities_ticker ON securities_new (ticker)")

            # Copy unique securities (first entry for each ticker)
            print("Copying unique securities to new table structure...")
            db.engine.execute("""
            INSERT INTO securities_new (
                ticker, name, exchange, asset_type, sector, currency, 
                current_price, added_at, updated_at
            )
            SELECT DISTINCT ON (ticker)
                ticker, name, exchange, asset_type, sector, currency, 
                current_price, added_at, updated_at
            FROM securities
            ORDER BY ticker, id
            """)

            # Count records in new table
            count_result = db.engine.execute("SELECT COUNT(*) FROM securities_new").fetchone()
            print(f"Created {count_result[0]} unique securities records")

            # Update foreign keys in portfolio_securities to point to the correct security IDs
            print("Updating references in portfolio_securities...")
            db.engine.execute("""
            UPDATE portfolio_securities ps
            SET security_id = sn.id
            FROM securities s
            JOIN securities_new sn ON s.ticker = sn.ticker
            WHERE ps.security_id = s.id
            """)

            # Count updates
            count_updated = db.engine.execute("""
            SELECT COUNT(*) FROM portfolio_securities
            """).fetchone()[0]

            print(f"Updated {count_updated} portfolio-security relationships")

            # Backup old securities table
            db.engine.execute("ALTER TABLE securities RENAME TO securities_old")

            # Rename new table to securities
            db.engine.execute("ALTER TABLE securities_new RENAME TO securities")

            print("Securities table structure updated successfully")
            return True

        except Exception as e:
            print(f"Error updating securities structure: {str(e)}")
            print(traceback.format_exc())
            return False


if __name__ == "__main__":
    # Run the migration steps
    print("Starting database migration...")

    # Step 1: Create portfolio_securities junction table
    if create_portfolio_securities_table():
        print("\nStep 1 completed: Portfolio securities junction table created and populated")

        # Step 2: Update securities table structure
        # Uncommenting this will execute the second step
        # if update_securities_structure():
        #     print("\nStep 2 completed: Securities table structure updated")
        # else:
        #     print("\nStep 2 failed: Securities table structure not updated")
    else:
        print("\nStep 1 failed: Junction table creation failed")