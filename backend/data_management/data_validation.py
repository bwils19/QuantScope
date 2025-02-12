from datetime import datetime
import pandas as pd
import numpy as np


class HistoricalDataValidator:
    @staticmethod
    def validate_record(record):
        """Validate a single historical data record"""
        try:
            # Basic validation rules
            assert isinstance(record['date'], datetime)
            assert all(isinstance(record[f], (int, float))
                       for f in ['open', 'high', 'low', 'close', 'volume'])
            assert record['high'] >= record['low']
            assert record['high'] >= record['open']
            assert record['high'] >= record['close']
            assert record['low'] <= record['open']
            assert record['low'] <= record['close']
            assert record['volume'] >= 0

            # Check for unreasonable values ?? - unclear on what these should be, starting here though
            assert record['high'] < 1000000
            assert record['volume'] < 1000000000

            return True
        except AssertionError:
            return False

    @staticmethod
    def clean_data(data):
        """Clean and normalize historical data"""
        df = pd.DataFrame(data)

        # handle missing values
        df = df.fillna(method='ffill')

        # Remove outliers
        for col in ['open', 'high', 'low', 'close']:
            z_scores = np.abs((df[col] - df[col].mean()) / df[col].std())
            df.loc[z_scores > 3, col] = np.nan

        # Final forward fill for any new NaNs
        df = df.fillna(method='ffill')

        return df.to_dict('records')