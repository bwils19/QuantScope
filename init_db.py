import psycopg2
import sys
from datetime import datetime


def create_junction_table():
    """Create the portfolio_securities junction table"""
    try:
        # Replace these with your actual database connection details
        conn = psycopg2.connect(
            host="quantscope-fellowship-do-user-19215750-0.l.db.ondigitalocean.com",
            # e.g., db-postgresql-nyc1-12345.db.ondigitalocean.com
            database="defaultdb",  # e.g., quantscope
            user="doadmin",  # e.g., doadmin
            password="AVNS_1Wwzrqn8pdJgU_-8Hud",  # Your actual password
            port="25060"  # Default DO Postgres port is usually 25060
        )

        print("Connected to database successfully")
        cursor = conn.cursor()

        # Check if the table already exists
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portfolio_securities')")
        table_exists = cursor.fetchone()[0]

        if not table_exists:
            print("\nCreating portfolio_securities junction table...")

            # Create the table
            cursor.execute("""
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
            """)

            # Migrate data from securities table to junction table
            print("Migrating data from securities table...")
            cursor.execute("""
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
            """)

            # Get counts for verification
            cursor.execute("SELECT COUNT(*) FROM portfolio_securities")
            junction_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM securities")
            security_count = cursor.fetchone()[0]

            print(f"Verification: {junction_count} records in junction table")
            print(f"Original securities count: {security_count}")
            print(f"Migration {'successful' if junction_count == security_count else 'incomplete'}")

            # Show the table structure
            cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'portfolio_securities'
            """)
            columns = cursor.fetchall()

            print("\nVerifying portfolio_securities table columns:")
            for col_name, col_type in columns:
                print(f"  - {col_name}: {col_type}")

            # Commit the transaction
            conn.commit()
            print("Transaction committed successfully.")

        else:
            print("\nPortfolio securities junction table already exists.")

        # Close the connection
        cursor.close()
        conn.close()
        print("Database connection closed.")

        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        if 'conn' in locals() and conn:
            conn.rollback()
            conn.close()
        return False


if __name__ == "__main__":
    print("Creating portfolio_securities junction table...")
    success = create_junction_table()

    if success:
        print("Migration completed successfully!")
    else:
        print("Migration failed.")
        sys.exit(1)