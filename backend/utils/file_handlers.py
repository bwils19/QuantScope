import pandas as pd
import os
import numpy as np


def standardize_columns(df):
    """
    Map common column names to standard names and rename columns
    """
    # First, standardize the column names
    df.columns = [col.lower().strip().replace('($)', '').strip() for col in df.columns]

    # Define mapping of alternative names to standard names
    column_mappings = {
        'ticker': ['ticker', 'symbol', 'stock', 'security'],
        'amount': ['amount', 'shares', 'quantity', 'position', 'units', 'share quantity'],
        'purchase_date': ['date purchased', 'purchase date', 'entry date', 'acquisition date', 'date'],
        'purchase_price': ['purchase price', 'purchase price', 'cost basis', 'entry price', 'buying price'],
        'current_price': ['current price', 'current price', 'market price', 'last price'],
        'sector': ['sector', 'industry'],
        'notes': ['notes', 'comments', 'description']
    }

    # Create reverse mapping
    reverse_mapping = {}
    for standard, alternatives in column_mappings.items():
        for alt in alternatives:
            reverse_mapping[alt.lower().strip()] = standard

    # Create new column mapping
    new_columns = {}
    for col in df.columns:
        if col in reverse_mapping:
            new_columns[col] = reverse_mapping[col]

    # Rename columns
    df = df.rename(columns=new_columns)

    print("After standardization, columns are:", df.columns.tolist())
    return df


def parse_portfolio_file(file_path):
    """Parse and validate portfolio file"""
    try:
        # Read the file
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext == '.csv':
            df = pd.read_csv(file_path)
        elif file_ext in ['.xls', '.xlsx']:
            df = pd.read_excel(file_path)
        elif file_ext == '.txt':
            df = pd.read_csv(file_path, sep='\t')
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        print("Original columns:", df.columns.tolist())

        # Standardize column names
        df = standardize_columns(df)
        print("Standardized columns:", df.columns.tolist())

        # Initialize validation
        df['validation_status'] = 'valid'
        df['validation_message'] = ''

        # Validate required columns
        if 'ticker' not in df.columns:
            raise ValueError("Missing 'ticker' column. Please ensure your file has a ticker/symbol column.")
        if 'amount' not in df.columns:
            raise ValueError("Missing 'amount' column. Please ensure your file has a shares/quantity column.")

        # Clean and validate data
        df['ticker'] = df['ticker'].str.strip().str.upper()
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

        # Mark invalid rows
        invalid_tickers = df['ticker'].str.contains(r'[^A-Z\.]').fillna(True)
        invalid_amounts = df['amount'].isna() | (df['amount'] <= 0)

        df.loc[invalid_tickers, 'validation_status'] = 'invalid'
        df.loc[invalid_tickers, 'validation_message'] += 'Invalid ticker format; '
        df.loc[invalid_amounts, 'validation_status'] = 'invalid'
        df.loc[invalid_amounts, 'validation_message'] += 'Invalid amount; '

        # Handle optional numeric columns
        for col in ['purchase_price', 'current_price']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        # Generate summary
        validation_summary = {
            'total_rows': len(df),
            'valid_rows': len(df[df['validation_status'] == 'valid']),
            'invalid_rows': len(df[df['validation_status'] == 'invalid']),
            'total_amount': float(df.loc[df['validation_status'] == 'valid', 'amount'].sum()),
            'unique_securities': len(df.loc[df['validation_status'] == 'valid', 'ticker'].unique())
        }

        return df, validation_summary

    except Exception as e:
        print(f"Error in parse_portfolio_file: {str(e)}")
        raise


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
                'purchase_date': row['purchase_date'] if not pd.isna(row['purchase_date']) else '',
                'purchase_price': float(row['purchase_price']) if not pd.isna(row['purchase_price']) else '',
                'current_price': float(row['current_price']) if not pd.isna(row['current_price']) else '',
                'sector': row['sector'] if not pd.isna(row['sector']) else '',
                'notes': row['notes'] if not pd.isna(row['notes']) else '',
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
