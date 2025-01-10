# test_cache.py
from backend.app import create_app
from backend.models import StockCache, Security, Portfolio
from datetime import datetime


def check_cache_and_prices():
    app = create_app()
    with app.app_context():
        print("\nStock Cache Entries:")
        caches = StockCache.query.all()
        for cache in caches:
            print(f"\nTicker: {cache.ticker}")
            print(f"Last Updated: {cache.date}")
            print(f"Data: {cache.data}")

        print("\nPortfolio Securities:")
        portfolios = Portfolio.query.all()
        for portfolio in portfolios:
            print(f"\nPortfolio: {portfolio.name}")
            print(f"Total Value: ${portfolio.total_value:,.2f}")
            print(f"Day Change: ${portfolio.day_change:,.2f} ({portfolio.day_change_pct:.2f}%)")
            print("\nSecurities:")
            for security in portfolio.securities:
                print(f"- {security.ticker}: ${security.current_price:,.2f} (Change: ${security.value_change:,.2f})")


if __name__ == "__main__":
    check_cache_and_prices()