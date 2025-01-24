from backend.app import create_app
from backend import db
from backend.models import User, Security, Portfolio
from sqlalchemy import inspect, text

app = create_app()  # Create the app instance

with app.app_context():
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
    print("Actual Database Path:", db.engine.url)

    # Drop all tables
    print("Dropping all tables...")
    db.drop_all()
    print("All tables dropped.")

    # Create all tables with new schema
    print("Creating all tables...")
    db.create_all()
    print("All tables created.")

    # Verify the securities table schema
    inspector = inspect(db.engine)
    print("\nVerifying securities table columns:")
    columns = inspector.get_columns('securities')
    for column in columns:
        print(f"  - {column['name']}: {column['type']}")

