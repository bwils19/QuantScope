from datetime import datetime, time
import pandas as pd
import pytz
from pandas_market_calendars import get_calendar


class MarketUtils:
    def __init__(self):
        self.nyse = get_calendar('NYSE')
        self.et_tz = pytz.timezone('US/Eastern')

    def get_current_market_time(self):
        """Get current time in ET"""
        return datetime.now(self.et_tz)

    def is_market_open(self):
        """Check if market is currently open"""
        current_time = self.get_current_market_time()

        # Check if it's a weekend
        if current_time.weekday() >= 5:
            return False

        # Get market schedule for today
        schedule = self.nyse.schedule(
            start_date=current_time.date(),
            end_date=current_time.date()
        )

        if schedule.empty:
            return False

        market_open = schedule.iloc[0]['market_open'].tz_convert(self.et_tz)
        market_close = schedule.iloc[0]['market_close'].tz_convert(self.et_tz)

        return market_open <= current_time <= market_close

    def get_last_trading_day(self):
        """Get the most recent completed trading day"""
        current_time = self.get_current_market_time()

        # Get recent trading days
        trading_days = self.nyse.valid_days(
            start_date=current_time - pd.Timedelta(days=10),
            end_date=current_time
        )

        # If current time is before market close (4 PM ET), use previous day
        if current_time.time() < time(16, 0):
            trading_days = trading_days[trading_days < current_time.floor('D')]

        return trading_days[-1].date()

    def should_fetch_market_data(self):
        """Determine if we should fetch new market data"""
        current_time = self.get_current_market_time()

        # Don't update on weekends
        if current_time.weekday() >= 5:
            return False, "Weekend - market closed"

        # Check if it's a market holiday
        schedule = self.nyse.schedule(
            start_date=current_time.date(),
            end_date=current_time.date()
        )
        if schedule.empty:
            return False, "Market holiday"

        # If before market close, don't fetch as data won't be final
        market_close_time = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
        if current_time < market_close_time:
            return False, "Market still open - data not final"

        # If after 8 PM ET, data should be available
        data_available_time = current_time.replace(hour=20, minute=0, second=0, microsecond=0)
        if current_time < data_available_time:
            return False, "Waiting for end-of-day data to be available"

        return True, "Market data ready for update"
