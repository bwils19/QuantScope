from backend import db, app

# Recreate the database
with app.app_context():
    db.create_all()
    print("Database and tables created successfully!")
