# test_files.py
from backend.app import create_app
from backend.models import PortfolioFiles, User


def check_files():
    app = create_app()
    with app.app_context():
        print("\nUsers:")
        users = User.query.all()
        for user in users:
            print(f"User ID: {user.id}, Email: {user.email}")

        print("\nPortfolio Files:")
        files = PortfolioFiles.query.all()
        for file in files:
            print(f"File ID: {file.id}")
            print(f"Filename: {file.filename}")
            print(f"Uploaded by: {file.uploaded_by}")
            print(f"Upload date: {file.uploaded_at}")
            print("-" * 50)


if __name__ == "__main__":
    check_files()