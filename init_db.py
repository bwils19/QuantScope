import psycopg2
import os
from dotenv import load_dotenv
import sys
from datetime import datetime

# Load environment variables to get database connection details
load_dotenv()


def get_db_connection():
    """Connect directly to the database using credentials from environment vars"""
    # Get database connection parameters from environment variables
    db_host = os.getenv('DB_HOST')
    db_name = os.getenv('DB_NAME')
    db_user = os.getenv('DB_USER')
    db_password = os.getenv('DB_PASSWORD')
    db_port = os.getenv('DB_PORT', '5432')  # Default PostgreSQL port

    print(f"Connecting to database {db_name} on {db_host}:{db_port} as {db_user}")

    # Connect to the database
    conn = psycopg2.connect(
        host=db_host,
        database=db_name,
        user=db_user,
        password=db_password,
        port=db_port
    )

    return conn


def create_junction_table(conn):
    """Create the portfolio_securities junction table"""
    try:
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

        return True

    except Exception as e:
        print(f"Error: {str(e)}")
        conn.rollback()
        return False


if __name__ == "__main__":
    print("Creating portfolio_securities junction table...")
    try:
        # Connect to the database
        conn = get_db_connection()

        # Create the junction table
        success = create_junction_table(conn)

        # Close the connection
        conn.close()

        if success:
            print("Migration completed successfully!")
        else:
            print("Migration failed.")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)