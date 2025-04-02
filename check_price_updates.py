#!/usr/bin/env python3
"""
Script to check if price updates are working correctly.
This script queries the database to see when the last price update occurred
and when the last historical data update occurred.
"""
import os
import sys
from datetime import datetime, timedelta
import argparse

# Add the current directory to the path so we can import the backend modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description='Check price update status')
    parser.add_argument('--days', type=int, default=7, 
                        help='Number of days to look back for updates')
    args = parser.parse_args()
    
    print(f"Checking price update status at {datetime.now()}")
    
    # Import after parsing args to avoid slow imports if help is requested
    from backend.app import create_app
    from backend.models import StockCache, SecurityHistoricalData, HistoricalDataUpdateLog
    from sqlalchemy import func, desc
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        # Check StockCache
        print("\n=== Stock Cache Status ===")
        latest_cache = StockCache.query.order_by(StockCache.date.desc()).first()
        if latest_cache:
            print(f"Latest cache entry: {latest_cache.ticker} on {latest_cache.date}")
            
            # Check how many tickers were updated on the latest date
            latest_date = latest_cache.date
            count = StockCache.query.filter_by(date=latest_date).count()
            print(f"Number of tickers updated on {latest_date}: {count}")
            
            # Check if the cache is stale
            today = datetime.now().date()
            days_old = (today - latest_date).days
            if days_old > 1:
                print(f"WARNING: Cache is {days_old} days old!")
            else:
                print("Cache is up to date.")
        else:
            print("No cache entries found!")
        
        # Check SecurityHistoricalData
        print("\n=== Historical Data Status ===")
        latest_historical = SecurityHistoricalData.query.order_by(
            SecurityHistoricalData.date.desc()).first()
        if latest_historical:
            print(f"Latest historical entry: {latest_historical.ticker} on {latest_historical.date}")
            
            # Check how many tickers were updated on the latest date
            latest_date = latest_historical.date
            count = SecurityHistoricalData.query.filter_by(date=latest_date).count()
            print(f"Number of tickers with historical data on {latest_date}: {count}")
            
            # Check if the historical data is stale
            today = datetime.now().date()
            days_old = (today - latest_date).days
            if days_old > 1:
                print(f"WARNING: Historical data is {days_old} days old!")
            else:
                print("Historical data is up to date.")
        else:
            print("No historical data entries found!")
        
        # Check HistoricalDataUpdateLog
        print("\n=== Update Log Status ===")
        latest_log = HistoricalDataUpdateLog.query.order_by(
            HistoricalDataUpdateLog.update_time.desc()).first()
        if latest_log:
            print(f"Latest update log: {latest_log.update_time}")
            print(f"Status: {latest_log.status}")
            print(f"Tickers updated: {latest_log.tickers_updated}")
            print(f"Records added: {latest_log.records_added}")
            if latest_log.error:
                print(f"Error: {latest_log.error}")
                
            # Check if the log is stale
            now = datetime.now()
            hours_old = (now - latest_log.update_time).total_seconds() / 3600
            if hours_old > 24:
                print(f"WARNING: Last update log is {hours_old:.1f} hours old!")
            else:
                print(f"Last update was {hours_old:.1f} hours ago.")
        else:
            print("No update logs found!")
        
        # Check recent updates
        print(f"\n=== Updates in the Last {args.days} Days ===")
        cutoff_date = datetime.now() - timedelta(days=args.days)
        
        # Count cache updates by date
        cache_updates = StockCache.query.with_entities(
            StockCache.date, func.count().label('count')
        ).group_by(StockCache.date).order_by(desc(StockCache.date)).all()
        
        print("Cache updates by date:")
        for date, count in cache_updates:
            if date >= cutoff_date.date():
                print(f"  {date}: {count} tickers")
        
        # Count historical data updates by date
        historical_updates = SecurityHistoricalData.query.with_entities(
            SecurityHistoricalData.date, func.count().label('count')
        ).group_by(SecurityHistoricalData.date).order_by(desc(SecurityHistoricalData.date)).all()
        
        print("\nHistorical data updates by date:")
        for date, count in historical_updates:
            if date >= cutoff_date.date():
                print(f"  {date}: {count} records")
        
        # Count update logs by date
        log_updates = HistoricalDataUpdateLog.query.with_entities(
            func.date(HistoricalDataUpdateLog.update_time).label('date'), 
            func.count().label('count')
        ).group_by('date').order_by(desc('date')).all()
        
        print("\nUpdate logs by date:")
        for date, count in log_updates:
            if date >= cutoff_date.date():
                print(f"  {date}: {count} logs")

if __name__ == "__main__":
    main()