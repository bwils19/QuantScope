import time
from backend import db
from models import Security
from datetime import datetime
from backend.services.price_update_service import PriceUpdateService as pus


def enrich_all_securities():
    tickers = db.session.query(Security.ticker).distinct().all()
    tickers = [t[0] for t in tickers]

    calls_this_minute = 0
    start_time = time.time()

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Updating {ticker}...")

        try:
            overview = pus.get_security_overview(ticker)
            quote = pus.get_global_quote(ticker)

            security = Security.query.filter_by(ticker=ticker).first()
            if not security:
                print(f"  Skipping {ticker}: not in DB")
                continue

            # Populate fields
            security.name = overview.get("Name", security.name)
            security.exchange = overview.get("Exchange", security.exchange)
            security.asset_type = overview.get("AssetType", security.asset_type)
            security.sector = overview.get("Sector", security.sector)
            security.currency = overview.get("Currency", security.currency)

            global_data = quote.get("Global Quote", {})
            if global_data:
                security.current_price = float(global_data.get("05. price", 0))
                security.previous_close = float(global_data.get("08. previous close", 0))

            security.updated_at = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            print(f"  Error updating {ticker}: {str(e)}")
            db.session.rollback()

        calls_this_minute += 2  # 1 call for each endpoint

        # Enforce 75 call/min limit
        if calls_this_minute >= 70:
            elapsed = time.time() - start_time
            if elapsed < 60:
                wait_time = 60 - elapsed
                print(f"Rate limit reached. Sleeping for {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            calls_this_minute = 0
            start_time = time.time()


if __name__ == "__main__":
    enrich_all_securities()
