import pandas as pd
from typing import Any


def is_date(value: Any) -> bool:
    """
    Check if a value can be parsed as a date
    """
    print(pd.Timestamp.today())

    if pd.isna(value):
        return False

    try:
        if pd.to_datetime(str(value)):
            # check if date is a future date
            if pd.to_datetime(str(value)) > pd.Timestamp.today():
                print("Date is a future date")
                return False
            else:
                return True
        else:
            return False
    except (ValueError, TypeError):
        return False
