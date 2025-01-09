# test_db.py
from backend.app import create_app
from backend.models import User, Portfolio, Security


def check_database():
    app = create_app()
    with app.app_context():
        print("\nUsers:")
        users = User.query.all()
        for user in users:
            print(f"User ID: {user.id}, Email: {user.email}")

        print("\nPortfolios:")
        portfolios = Portfolio.query.all()
        for portfolio in portfolios:
            print(f"Portfolio ID: {portfolio.id}, Name: {portfolio.name}, User ID: {portfolio.user_id}")
            print(f"Holdings: {portfolio.total_holdings}")

            print("\nSecurities in this portfolio:")
            securities = Security.query.filter_by(portfolio_id=portfolio.id).all()
            for security in securities:
                print(f"  {security.ticker}: {security.amount_owned} shares, Value: {security.total_value}")
            print("-" * 50)


if __name__ == "__main__":
    check_database()