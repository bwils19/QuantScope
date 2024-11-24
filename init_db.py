from backend import db, app
from backend.models import User
from sqlalchemy import inspect
from sqlalchemy.schema import CreateTable

with app.app_context():
    # Debugging: Print database URI and path
    print("Database URI:", app.config['SQLALCHEMY_DATABASE_URI'])
    print("Actual Database Path:", db.engine.url)

    # Drop all tables to reset schema
    db.drop_all()
    print("Dropped all tables.")

    # Create all tables
    db.create_all()
    print("Created all tables.")

    # Verify tables
    inspector = inspect(db.engine)
    print("Tables in database:", inspector.get_table_names())

    # Print SQL used to create User table (debugging)
    print("User table SQL:")
    print(CreateTable(User.__table__).compile(db.engine))
