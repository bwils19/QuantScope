import pandas as pd
import os
import numpy as np
import re
from datetime import datetime
from typing import Dict, Tuple, List, Any, Optional


def clean_column_name(name: str) -> str:
    """
    clean column namea by removing special characters and standardizing spacing
    """
    # remove special characters but keep spaces and underscores temporarily
    cleaned = re.sub(r'[^a-zA-Z0-9\s_]', '', name.lower())
    # Replace underscores and multiple spaces with single space
    cleaned = re.sub(r'[_\s]+', ' ', cleaned)
    return cleaned.strip()


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


def parse_portfolio_file(file_obj, file_ext: str = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Parse and validate portfolio file with improved error handling and validation
    
    Args:
        file_obj: Either a file path string or a file-like object
        file_ext: Optional file extension (required if file_obj is a file-like object)
    """
    try:
        # Determine if we're dealing with a file path or a file object
        if isinstance(file_obj, str):
            file_path = file_obj
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Read from file path
            if file_ext == '.csv':
                df = pd.read_csv(file_path)
            elif file_ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_path)
            elif file_ext == '.txt':
                df = pd.read_csv(file_path, sep='\t')
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
        else:
            # Read from file object
            if not file_ext:
                raise ValueError("File extension must be provided when using a file object")
                
            # Reset file pointer to beginning
            file_obj.seek(0)
            
            if file_ext == '.csv':
                df = pd.read_csv(file_obj)
            elif file_ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_obj)
            elif file_ext == '.txt':
                df = pd.read_csv(file_obj, sep='\t')
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")

        # standardize column names
        df = standardize_columns(df)

        # initialize validation
        df['validation_status'] = 'valid'
        df['validation_message'] = ''

        # validate required columns
        missing_columns = []
        for col in ['ticker', 'amount']:
            if col not in df.columns:
                missing_columns.append(col)

        if missing_columns:
            raise ValueError(
                f"Missing required columns: {', '.join(missing_columns)}. "
                "Please ensure your file has ticker and amount/quantity columns."
            )

        df['ticker'] = df['ticker'].str.strip().str.upper()
        df['amount'] = pd.to_numeric(df['amount'], errors='coerce')

        invalid_tickers = df['ticker'].str.contains(r'[^A-Z\.]', na=True).astype(bool)
        invalid_amounts = df['amount'].isna() | (df['amount'] <= 0)

        df.loc[invalid_tickers, 'validation_status'] = 'invalid'
        df.loc[invalid_tickers, 'validation_message'] += 'Invalid ticker format; '
        df.loc[invalid_amounts, 'validation_status'] = 'invalid'
        df.loc[invalid_amounts, 'validation_message'] += 'Invalid amount; '

        # Handle optional numeric columns
        numeric_columns = ['purchase_price', 'current_price']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                invalid_prices = df[col].isna() & df[col].notna()
                if invalid_prices.any():
                    df.loc[invalid_prices, 'validation_status'] = 'invalid'
                    df.loc[invalid_prices, 'validation_message'] += f'Invalid {col}; '

        # validation summary
        validation_summary = {
            'total_rows': len(df),
            'valid_rows': len(df[df['validation_status'] == 'valid']),
            'invalid_rows': len(df[df['validation_status'] == 'invalid']),
            'total_amount': float(df.loc[df['validation_status'] == 'valid', 'amount'].sum()),
            'unique_securities': len(df.loc[df['validation_status'] == 'valid', 'ticker'].unique()),
            'columns_found': df.columns.tolist(),
            'missing_columns': missing_columns,
            'validation_time': datetime.now().isoformat()
        }

        return df, validation_summary

    except Exception as e:
        print(f"Error in parse_portfolio_file: {str(e)}")
        raise


def format_preview_data(df):
    """
    Format DataFrame for preview display with required and optional columns
    Returns JSON-safe dictionary with validation information
    """
    try:
        preview_data = []

        # required and optional columns
        required_columns = {
            'ticker': str,
            'amount': float,
            'purchase_date': str
        }
        # i can implement an api call later to grab this information if it isn't provided in the file.
        optional_columns = {
            'name': str,
            'purchase_price': float,
            'current_price': float,
            'sector': str,
            'exchange': str,
            'notes': str
        }

        for _, row in df.iterrows():
            preview_row = {
                'validation_status': row.get('validation_status', 'valid'),  # Default to valid
                'validation_message': row.get('validation_message', '').strip('; ')
            }

            # Handle required columns
            for col, dtype in required_columns.items():
                if col not in row:
                    preview_row[col] = 'Missing'
                    preview_row['validation_status'] = 'invalid'
                    preview_row['validation_message'] += f'Missing required column: {col}; '
                else:
                    try:
                        if col == 'purchase_date':
                            # Handle date specifically
                            if pd.isna(row[col]):
                                preview_row[col] = 'Missing'
                                preview_row['validation_status'] = 'invalid'
                                preview_row['validation_message'] += 'Missing purchase date; '
                            else:
                                preview_row[col] = str(row[col])
                        elif dtype == float:
                            preview_row[col] = float(row[col]) if not pd.isna(row[col]) else 'Invalid'
                            if pd.isna(row[col]) or float(row[col]) <= 0:
                                preview_row['validation_status'] = 'invalid'
                                preview_row['validation_message'] += f'Invalid {col}; '
                        else:
                            preview_row[col] = str(row[col]) if not pd.isna(row[col]) else 'Invalid'
                            if pd.isna(row[col]):
                                preview_row['validation_status'] = 'invalid'
                                preview_row['validation_message'] += f'Invalid {col}; '
                    except (ValueError, TypeError):
                        preview_row[col] = 'Invalid'
                        preview_row['validation_status'] = 'invalid'
                        preview_row['validation_message'] += f'Invalid {col} format; '

            # Handle optional columns
            for col, dtype in optional_columns.items():
                if col in row.index:
                    try:
                        if dtype == float and not pd.isna(row[col]):
                            preview_row[col] = float(row[col])
                        elif not pd.isna(row[col]):
                            preview_row[col] = str(row[col])
                        else:
                            preview_row[col] = ''
                    except (ValueError, TypeError):
                        preview_row[col] = ''
                else:
                    preview_row[col] = ''  # Set empty string for missing optional columns

            preview_data.append(preview_row)

        return preview_data
    except Exception as e:
        print(f"Error in format_preview_data: {str(e)}")
        raise


def validate_portfolio_file(file_obj, file_ext: str = None) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Validate uploaded file with enhanced error handling, security checks, and reporting
    
    Args:
        file_obj: Either a file path string or a file-like object
        file_ext: Optional file extension (required if file_obj is a file-like object)
    """
    import logging
    from backend.utils.file_validators import validate_uploaded_file, safe_read_file
    
    logger = logging.getLogger('file_handlers')
    
    try:
        # If it's a string (file path), we'll use the traditional method
        if isinstance(file_obj, str):
            df, validation_summary = parse_portfolio_file(file_obj, file_ext)
            
            message = (
                f"File validated successfully:\n"
                f"- Total securities: {validation_summary.get('total_securities', validation_summary.get('unique_securities', 0))}\n"
                f"- Unique securities: {validation_summary['unique_securities']}\n"
                f"- Total position amount: {validation_summary['total_amount']:,.2f}\n"
                f"- Valid rows: {validation_summary['valid_rows']}\n"
                f"- Invalid rows: {validation_summary['invalid_rows']}"
            )

            # warning if there are invalid rows
            if validation_summary['invalid_rows'] > 0:
                message += "\n\nWarning: Some rows contain invalid data. Check the preview for details."

            return True, message, df
        
        # For file objects, use the new secure validator
        else:
            logger.info(f"Validating uploaded file: {getattr(file_obj, 'filename', 'unknown')}")
            
            # First perform security validation
            success, message, data = safe_read_file(file_obj)
            
            if not success:
                logger.warning(f"File validation failed: {message}")
                return False, message, None
            
            # If we got here, the file passed security checks and we have the dataframe
            df = data
            
            # Now perform the business logic validation
            df = standardize_columns(df)
            
            # Initialize validation
            df['validation_status'] = 'valid'
            df['validation_message'] = ''
            
            # Validate required columns
            missing_columns = []
            for col in ['ticker', 'amount']:
                if col not in df.columns:
                    missing_columns.append(col)
            
            if missing_columns:
                error_msg = (
                    f"Missing required columns: {', '.join(missing_columns)}. "
                    "Please ensure your file has ticker and amount/quantity columns."
                )
                logger.warning(error_msg)
                return False, error_msg, None
            
            # Validate data
            df['ticker'] = df['ticker'].str.strip().str.upper()
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
            
            invalid_tickers = df['ticker'].str.contains(r'[^A-Z\.]', na=True).astype(bool)
            invalid_amounts = df['amount'].isna() | (df['amount'] <= 0)
            
            df.loc[invalid_tickers, 'validation_status'] = 'invalid'
            df.loc[invalid_tickers, 'validation_message'] += 'Invalid ticker format; '
            df.loc[invalid_amounts, 'validation_status'] = 'invalid'
            df.loc[invalid_amounts, 'validation_message'] += 'Invalid amount; '
            
            # Handle optional numeric columns
            numeric_columns = ['purchase_price', 'current_price']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                    invalid_prices = df[col].isna() & df[col].notna()
                    if invalid_prices.any():
                        df.loc[invalid_prices, 'validation_status'] = 'invalid'
                        df.loc[invalid_prices, 'validation_message'] += f'Invalid {col}; '
            
            # Create validation summary
            validation_summary = {
                'total_rows': len(df),
                'valid_rows': len(df[df['validation_status'] == 'valid']),
                'invalid_rows': len(df[df['validation_status'] == 'invalid']),
                'total_amount': float(df.loc[df['validation_status'] == 'valid', 'amount'].sum()),
                'unique_securities': len(df.loc[df['validation_status'] == 'valid', 'ticker'].unique()),
                'columns_found': df.columns.tolist(),
                'missing_columns': missing_columns,
                'validation_time': datetime.now().isoformat()
            }
            
            message = (
                f"File validated successfully:\n"
                f"- Total securities: {validation_summary.get('total_securities', validation_summary.get('unique_securities', 0))}\n"
                f"- Unique securities: {validation_summary['unique_securities']}\n"
                f"- Total position amount: {validation_summary['total_amount']:,.2f}\n"
                f"- Valid rows: {validation_summary['valid_rows']}\n"
                f"- Invalid rows: {validation_summary['invalid_rows']}"
            )
            
            # Warning if there are invalid rows
            if validation_summary['invalid_rows'] > 0:
                message += "\n\nWarning: Some rows contain invalid data. Check the preview for details."
            
            logger.info(f"File validation successful: {validation_summary['valid_rows']} valid rows, {validation_summary['invalid_rows']} invalid rows")
            return True, message, df

    except Exception as e:
        logger.error(f"Error in validate_portfolio_file: {str(e)}", exc_info=True)
        return False, str(e), None


def analyze_column_content(df, column_name):
    """Analyze column content with amount vs price detection"""

    if len(df) == 0:
        return {
            'ticker': 0,
            'amount': 0,
            'price': 0,
            'date': 0
        }
    sample_data = df[column_name].head(100).fillna('')

    # Basic features
    features = {
        # unique ratios. higher ratio -> closer to 1, mostly unique values so most likely prices, or IDs etc.
        # closer to 0, then it's more likely to be something like categories or sectors etc.
        'unique_ratio': len(sample_data.unique()) / len(sample_data),
        # what can be converted to numeric
        'numeric_ratio': sum(pd.to_numeric(pd.Series(sample_data), errors='coerce').notna()) / len(sample_data),
        # string length meant to determine tickers from descriptions essentially.
        'string_length_mean': np.mean([len(str(x)) for x in sample_data]),
        # case ratio, tickers tend to be uppercase (but not always... haha that's why we have length too!)
        'uppercase_ratio': sum(str(x).isupper() for x in sample_data) / len(sample_data),
        # what can be parsed as a date
        'contains_date': sum(pd.Series(sample_data).apply(try_parse_date).notna()) / len(sample_data),
        # values containing decimals.
        'decimal_ratio': sum('.' in str(x) for x in sample_data) / len(sample_data),
        # values that are whole numbers.
        'whole_number_ratio': sum(
            float(x).is_integer() for x in pd.to_numeric(sample_data, errors='coerce').dropna()) / len(sample_data)
    }

    # scoring logic for required columns in dataset
    scores = {
        'ticker': (features['uppercase_ratio'] > 0.8 and
                   features['string_length_mean'] < 5 and
                   features['unique_ratio'] > 0.1),

        'amount': (features['numeric_ratio'] > 0.8 and
                   features['whole_number_ratio'] > 0.8 and  # most amounts are whole numbers
                   features['decimal_ratio'] < 0.2),  # few decimals in amounts

        'price': (features['numeric_ratio'] > 0.8 and
                  features['decimal_ratio'] > 0.5 and  # prices usually have decimals
                  features['unique_ratio'] > 0.3),  # prices tend to be more unique

        'date': features['contains_date'] > 0.8
    }

    return {k: float(v) for k, v in scores.items()}


def try_parse_date(value):
    """Attempt to parse date in multiple formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return pd.to_datetime(value, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def get_name_similarity(column_name, reference_terms):
    """Get similarity between column name and reference terms"""
    column_name = column_name.lower().strip()
    max_similarity = 0

    # Direct match!
    if column_name in [clean_column_name(term).lower() for term in reference_terms]:
        return 1.0

    # Word match
    column_words = set(column_name.split())
    for term in reference_terms:
        term = term.lower()  # Ensure term is lowercase
        term_words = set(term.split())
        intersection = column_words.intersection(term_words)
        if intersection:
            similarity = len(intersection) / max(len(column_words), len(term_words))
            max_similarity = max(max_similarity, similarity)

    return max_similarity


def smart_detect_columns(df):
    """Smart column detection combining multiple approaches"""
    print("=======SMART DETECT COLUMN CALLED===================")
    column_mappings = {
        'ticker': ['ticker', 'symbol', 'stock', 'security', 'ticker symbol', 'stock symbol', 'securities', 'asset'],
        'amount': ['amount', 'amount_owned', 'shares', 'quantity', 'position', 'units', 'share quantity', 'holdings',
                   'owned'],
        'purchase_date': ['date purchased', 'purchase date', 'entry date', 'acquisition date', 'date', 'purchase_date',
                          'transaction_date', 'date_transaction', 'buy_date'],
        'purchase_price': ['purchase price', 'cost basis', 'entry price', 'buying price', 'cost', 'price paid'],
        'current_price': ['current price', 'market price', 'last price', 'price', 'closing price'],
        'sector': ['sector', 'industry', 'sector classification', 'industry group', 'market_sector'],
        'notes': ['notes', 'comments', 'description', 'memo', 'details', 'additional info', 'remarks'],
        'company_name': ['company', 'name', 'company name', 'security name', 'description', 'company description',
                         'issuer', 'company_name', 'security_name', 'stock_name']
    }

    detected_columns = {}
    debug_info = {} if os.getenv('DEBUG') else None

    for col in df.columns:
        col_lower = col.lower().strip()
        content_scores = analyze_column_content(df, col)

        best_match = None
        best_score = 0

        for target_col, reference_terms in column_mappings.items():
            # Combine name similarity and content analysis
            # name_score = get_name_similarity(col_lower, [term.lower() for term in reference_terms])
            name_score = get_name_similarity(col_lower, reference_terms)
            content_score = content_scores.get(target_col, 0)

            # Weight the scores (adjust weights as needed)
            combined_score = (name_score * 0.7) + (content_score * 0.3)

            if combined_score > best_score and combined_score > 0.4:  # Threshold
                best_score = combined_score
                best_match = target_col

            if debug_info is not None:
                debug_info[col] = {
                    'name_score': name_score,
                    'content_score': content_score,
                    'combined_score': combined_score,
                    'best_match': best_match
                }

        if best_match:
            detected_columns[col] = best_match
    if debug_info:
        print("\nColumn Detection Debug Info:")
        for col, info in debug_info.items():
            print(f"\nColumn: {col}")
            print(f"Best Match: {info['best_match']}")
            print(f"Scores: Name={info['name_score']:.2f}, "
                  f"Content={info['content_score']:.2f}, "
                  f"Combined={info['combined_score']:.2f}")

    return detected_columns


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    column standardization with debug output
    """
    # First, standardize the column names
    df.columns = [clean_column_name(col) for col in df.columns]

    print("\nOriginal columns:", df.columns.tolist())

    # Use enhanced smart detection
    detected_mappings = smart_detect_columns(df)

    print("\nDetected mappings:")
    for orig_col, mapped_col in detected_mappings.items():
        print(f"  {orig_col} → {mapped_col}")

    # Rename columns based on detection
    df = df.rename(columns=detected_mappings)

    print("\nAfter standardization:", df.columns.tolist())
    return df


# # testing column detection
# df = pd.read_csv('full_sample_data.csv')
# print("Original columns:", df.columns)
# df = standardize_columns(df)
# print("Standardized columns:", df.columns)
