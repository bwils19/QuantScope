from backend.app import create_app
from backend.models import Security, SecurityHistoricalData
from backend import db


def fix_zero_prices():
    print("Starting to fix zero price securities...")

    # Get securities with zero prices
    zero_price_securities = Security.query.filter(
        (Security.current_price == 0) | (Security.current_price == None)
    ).all()

    print(f"Found {len(zero_price_securities)} securities with zero prices")

    # Group by ticker for efficiency
    ticker_securities = {}
    for security in zero_price_securities:
        ticker = security.ticker
        if ticker not in ticker_securities:
            ticker_securities[ticker] = []
        ticker_securities[ticker].append(security)

    print(f"Grouped into {len(ticker_securities)} unique tickers")

    fixed_count = 0

    # Process each ticker
    for ticker, securities in ticker_securities.items():
        print(f"Processing {ticker} with {len(securities)} instances...")

        # Try to get historical price
        historical_data = SecurityHistoricalData.query.filter_by(ticker=ticker).order_by(
            SecurityHistoricalData.date.desc()
        ).first()

        if historical_data and historical_data.close_price > 0:
            price = float(historical_data.close_price)
            print(f"  Using historical price from {historical_data.date}: ${price}")

            for security in securities:
                security.current_price = price
                security.total_value = security.amount_owned * price
                fixed_count += 1
        elif any(s.purchase_price and s.purchase_price > 0 for s in securities):
            # Use purchase price if available
            for security in securities:
                if security.purchase_price and security.purchase_price > 0:
                    price = security.purchase_price
                    print(f"  Using purchase price: ${price}")
                    security.current_price = price
                    security.total_value = security.amount_owned * price
                    fixed_count += 1
        else:
            print(f"  Could not find valid price for {ticker}")

    # Commit changes
    db.session.commit()
    print(f"Fixed {fixed_count}/{len(zero_price_securities)} securities")

    return {
        'total_securities': len(zero_price_securities),
        'fixed_count': fixed_count
    }


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        fix_zero_prices()