import pandas as pd
import os
import numpy as np


def standardize_columns(df):
    """
    Map common column names to standard names
    """
    column_mappings = {
        # will probably need to add to these or write some ML algo to determine?
        # Ticker mappings
        'ticker': ['ticker', 'symbol', 'stock', 'security'],

        # Amount/Shares mappings
        'amount': ['amount', 'shares', 'quantity', 'position', 'units', 'share quantity'],

        # Optional columns
        'name': ['name', 'security name', 'company', 'company name'],
        'exchange': ['exchange', 'market'],
        'purchase_price': ['purchase price', 'purchase price ($)', 'cost basis', 'entry price', 'buying price',
                           'buy price'],
        'current_price': ['current price', 'current price ($)', 'market price', 'last price'],
        'sector': ['sector', 'industry'],
        'purchase_date': ['date purchased', 'purchase date', 'entry date', 'acquisition date']
    }

    # Convert all column names to lowercase and remove special characters
    df.columns = [col.lower().strip().replace('($)', '').strip() for col in df.columns]

    # Create reverse mapping for easier lookup
    reverse_mapping = {}
    for standard, alternatives in column_mappings.items():
        for alt in alternatives:
            reverse_mapping[alt] = standard

    # Rename columns based on mappings
    new_columns = {}
    for col in df.columns:
        if col in reverse_mapping:
            new_columns[col] = reverse_mapping[col]

    return df.rename(columns=new_columns)


def parse_portfolio_file(file_path):
    """
    Parse uploaded portfolio file with detailed row validation
    Returns DataFrame with validation status for each row
    """
    print(f"Processing file: {file_path}")

    try:
        file_ext = os.path.splitext(file_path)[1].lower()
        print(f"File extension: {file_ext}")

        # Read file based on extension
        if file_ext == '.csv':
            df = pd.read_csv(file_path)
        elif file_ext in ['.xls', '.xlsx']:
            df = pd.read_excel(file_path)
        elif file_ext == '.txt':
            df = pd.read_csv(file_path, sep='\t')
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        print(f"Initial columns: {df.columns.tolist()}")

        # Standardize column names
        df = standardize_columns(df)
        print(f"Standardized columns: {df.columns.tolist()}")

        # Initialize validation columns
        df['validation_status'] = 'valid'
        df['validation_message'] = ''

        # Validate required columns exist
        required_columns = ['ticker', 'amount']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(
                f"Missing required columns: {', '.join(missing_columns)}. Please ensure your file contains ticker and amount/shares information.")

        # Validate ticker format
        df['ticker'] = df['ticker'].str.strip().str.upper()
        invalid_tickers = df['ticker'].str.contains(r'[^A-Z\.]').fillna(True)
        df.loc[invalid_tickers, 'validation_status'] = 'invalid'
        df.loc[invalid_tickers, 'validation_message'] += 'Invalid ticker format; '

        # Validate amounts
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        invalid_amounts = df['amount'].isna() | (df['amount'] <= 0)
        df.loc[invalid_amounts, 'validation_status'] = 'invalid'
        df.loc[invalid_amounts, 'validation_message'] += 'Invalid amount; '

        # Convert optional price columns if present
        if 'purchase_price' in df.columns:
            df['purchase_price'] = pd.to_numeric(df['purchase_price'], errors='coerce')
        if 'current_price' in df.columns:
            df['current_price'] = pd.to_numeric(df['current_price'], errors='coerce')

        # Generate validation summary
        validation_summary = {
            'total_rows': len(df),
            'valid_rows': len(df[df['validation_status'] == 'valid']),
            'invalid_rows': len(df[df['validation_status'] == 'invalid']),
            'total_amount': float(df.loc[df['validation_status'] == 'valid', 'amount'].sum()),
            'unique_securities': len(df.loc[df['validation_status'] == 'valid', 'ticker'].unique())
        }

        print("Validation summary:", validation_summary)
        return df, validation_summary

    except Exception as e:
        print(f"Error in parse_portfolio_file: {str(e)}")
        raise Exception(f"Error processing file: {str(e)}")


def format_preview_data(df):
    """
    Format DataFrame for preview display
    Returns JSON-safe dictionary with validation information
    """
    try:
        preview_data = []
        for _, row in df.iterrows():
            preview_row = {
                'ticker': row['ticker'],
                'amount': float(row['amount']) if not pd.isna(row['amount']) else 'Invalid',
                'name': row.get('name', ''),
                'exchange': row.get('exchange', ''),
                'purchase_price': float(row['purchase_price']) if 'purchase_price' in row and not pd.isna(
                    row['purchase_price']) else '',
                'current_price': float(row['current_price']) if 'current_price' in row and not pd.isna(
                    row['current_price']) else '',
                'sector': row.get('sector', ''),
                'purchase_date': row.get('purchase_date', ''),
                'validation_status': row['validation_status'],
                'validation_message': row['validation_message'].strip('; ')
            }
            preview_data.append(preview_row)

        return preview_data
    except Exception as e:
        print(f"Error in format_preview_data: {str(e)}")
        raise


def validate_portfolio_file(file_path):
    """
    Validate the uploaded file before processing
    Returns tuple (is_valid, message)
    """
    try:
        df = parse_portfolio_file(file_path)

        validation_results = {
            'total_securities': len(df),
            'unique_securities': len(df['ticker'].unique()),
            'total_amount': df['amount'].sum()
        }

        message = (
            f"File validated successfully:\n"
            f"- Total securities: {validation_results['total_securities']}\n"
            f"- Unique securities: {validation_results['unique_securities']}\n"
            f"- Total position amount: {validation_results['total_amount']:,.2f}"
        )

        return True, message, df

    except Exception as e:
        return False, str(e), None
