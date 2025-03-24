import psycopg2
import sys
from datetime import datetime


def create_junction_table():
    pass


if __name__ == "__main__":
    print("Creating portfolio_securities junction table...")
    success = create_junction_table()

    if success:
        print("Migration completed successfully!")
    else:
        print("Migration failed.")
        sys.exit(1)
461d9cc65230609fb64847bba6163ac400391e44