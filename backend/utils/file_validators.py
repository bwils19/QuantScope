"""
File validation utilities for secure file uploads.
"""

import os
import re
import magic
import hashlib
import logging
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import openpyxl
from werkzeug.datastructures import FileStorage

# Configure logging
logger = logging.getLogger('file_validators')

# Define allowed file types and their MIME types
ALLOWED_EXTENSIONS = {
    'csv': ['text/csv', 'text/plain', 'application/csv'],
    'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
    'xls': ['application/vnd.ms-excel'],
    'txt': ['text/plain']
}

# Maximum file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Potentially dangerous content patterns
DANGEROUS_PATTERNS = [
    # Shell command injection
    r'`.*`',                      # Backtick command execution
    r'\$\(.*\)',                  # Command substitution
    r';\s*rm\s',                  # Semicolon followed by rm command
    r';\s*wget\s',                # Semicolon followed by wget command
    r';\s*curl\s',                # Semicolon followed by curl command
    
    # Script tags and other HTML/JavaScript
    r'<script.*>',                # Script tags
    r'javascript:',               # JavaScript protocol
    r'onerror=',                  # Event handlers
    r'onload=',
    
    # SQL Injection
    r';\s*DROP\s+TABLE',          # DROP TABLE statements
    r';\s*DELETE\s+FROM',         # DELETE FROM statements
    r'UNION\s+SELECT',            # UNION SELECT statements
    
    # File path traversal
    r'\.\./\.\.',                 # Path traversal
    
    # Executable content
    r'PK\x03\x04',                # ZIP file header (could contain malicious files)
    r'MZ',                        # EXE file header
]

def validate_file_extension(filename: str) -> Tuple[bool, str]:
    """
    Validate that the file has an allowed extension.
    Args: filename: The name of the file to validate
    Returns: Tuple of (is_valid, message)
    """

    if not filename or '.' not in filename:
        return False, "Invalid filename or missing extension"
    
    extension = filename.rsplit('.', 1)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        return False, f"File extension '{extension}' not allowed. Allowed extensions: {', '.join(ALLOWED_EXTENSIONS.keys())}"
    
    return True, ""

def validate_file_size(file: FileStorage) -> Tuple[bool, str]:
    """
    Validate that the file size is within allowed limits.
    Args: file: The file object to validate
    Returns: Tuple of (is_valid, message)
    """

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)  # Reset file pointer
    
    if size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE / (1024 * 1024)}MB"
    
    return True, ""

def validate_file_content_type(file: FileStorage) -> Tuple[bool, str]:
    """
    Validate that the file content matches its claimed type using libmagic.
    Args: file: The file object to validate
    Returns: Tuple of (is_valid, message)
    """
    # Read a sample of the file
    file_sample = file.read(2048)
    file.seek(0)  # Reset file pointer
    
    # Use python-magic to detect the MIME type
    mime = magic.Magic(mime=True)
    detected_mime = mime.from_buffer(file_sample)
    
    # Get the extension from the filename
    extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    # Check if the detected MIME type is allowed for this extension
    if extension in ALLOWED_EXTENSIONS:
        allowed_mimes = ALLOWED_EXTENSIONS[extension]
        if detected_mime not in allowed_mimes:
            return False, f"File content doesn't match its extension. Detected: {detected_mime}"
    
    return True, ""

def scan_for_dangerous_content(file: FileStorage) -> Tuple[bool, str]:
    """
    Scan file content for potentially dangerous patterns.
    Args: file: The file object to scan
    Returns: Tuple of (is_safe, message)
    """
    # Read the file content
    content = file.read()
    file.seek(0)  # Reset file pointer
    
    # Convert binary content to string for pattern matching
    if isinstance(content, bytes):
        # Try to decode as UTF-8, but fall back to latin-1 which can decode any byte
        try:
            content_str = content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = content.decode('latin-1')
    else:
        content_str = content
    
    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, content_str, re.IGNORECASE):
            return False, "Potentially malicious content detected in file"
    
    return True, ""

def validate_csv_content(file: FileStorage) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Validate that the CSV file contains valid data.
    Args: file: The CSV file to validate
    Returns: Tuple of (is_valid, message, dataframe)
    """
    try:
        # Try to read the CSV file
        df = pd.read_csv(file, encoding='utf-8')
        file.seek(0)  # Reset file pointer
        
        # Check if the dataframe is empty
        if df.empty:
            return False, "CSV file is empty", None
        
        # Basic validation of required columns for portfolio data
        required_columns = ['ticker', 'amount']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}", None
        
        return True, "", df
    
    except pd.errors.EmptyDataError:
        return False, "CSV file is empty", None
    except pd.errors.ParserError:
        return False, "CSV file is not properly formatted", None
    except Exception as e:
        return False, f"Error reading CSV file: {str(e)}", None

def validate_excel_content(file: FileStorage) -> Tuple[bool, str, Optional[pd.DataFrame]]:
    """
    Validate that the Excel file contains valid data.
    Args: file: The Excel file to validate
    Returns: Tuple of (is_valid, message, dataframe)
    """
    try:
        # Try to read the Excel file
        df = pd.read_excel(file)
        file.seek(0)  # Reset file pointer
        
        # Check if the dataframe is empty
        if df.empty:
            return False, "Excel file is empty", None
        
        # Basic validation of required columns for portfolio data
        required_columns = ['ticker', 'amount']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}", None
        
        return True, "", df
    
    except Exception as e:
        return False, f"Error reading Excel file: {str(e)}", None

def validate_file_metadata(file: FileStorage) -> Dict[str, Any]:
    """
    Extract and validate file metadata.
    
    Args:
        file: The file to validate
        
    Returns:
        Dictionary containing file metadata
    """
    # Calculate file hash for integrity checking
    file_content = file.read()
    file.seek(0)  # Reset file pointer
    
    file_hash = hashlib.sha256(file_content).hexdigest()
    
    # Get file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)  # Reset file pointer
    
    # Get file extension
    extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    # Use python-magic to detect the MIME type
    mime = magic.Magic(mime=True)
    detected_mime = mime.from_buffer(file_content[:2048])
    
    return {
        'filename': file.filename,
        'size': file_size,
        'extension': extension,
        'mime_type': detected_mime,
        'hash': file_hash
    }

def validate_uploaded_file(file: FileStorage) -> Dict[str, Any]:
    """
    Comprehensive validation of an uploaded file.
    
    Args:
        file: The file to validate
        
    Returns:
        Dictionary with validation results
    """
    result = {
        'is_valid': False,
        'messages': [],
        'metadata': None,
        'data': None
    }
    
    # Validate file extension
    ext_valid, ext_msg = validate_file_extension(file.filename)
    if not ext_valid:
        result['messages'].append(ext_msg)
        return result
    
    # Validate file size
    size_valid, size_msg = validate_file_size(file)
    if not size_valid:
        result['messages'].append(size_msg)
        return result
    
    # Validate content type
    type_valid, type_msg = validate_file_content_type(file)
    if not type_valid:
        result['messages'].append(type_msg)
        return result
    
    # Scan for dangerous content
    safe, safety_msg = scan_for_dangerous_content(file)
    if not safe:
        result['messages'].append(safety_msg)
        return result
    
    # Extract metadata
    result['metadata'] = validate_file_metadata(file)
    
    # Validate file content based on type
    extension = file.filename.rsplit('.', 1)[1].lower()
    
    if extension == 'csv':
        content_valid, content_msg, df = validate_csv_content(file)
    elif extension in ['xlsx', 'xls']:
        content_valid, content_msg, df = validate_excel_content(file)
    elif extension == 'txt':
        # For text files, try to parse as CSV
        content_valid, content_msg, df = validate_csv_content(file)
    else:
        content_valid, content_msg, df = False, f"Unsupported file type: {extension}", None
    
    if not content_valid:
        result['messages'].append(content_msg)
        return result
    
    # If we got here, the file is valid
    result['is_valid'] = True
    result['data'] = df
    result['messages'].append("File validation successful")
    
    return result

def safe_read_file(file: FileStorage) -> Tuple[bool, str, Any]:
    """
    Safely read a file's contents based on its type.
    
    Args:
        file: The file to read
        
    Returns:
        Tuple of (success, message, data)
    """
    try:
        # First validate the file
        validation = validate_uploaded_file(file)
        
        if not validation['is_valid']:
            return False, "; ".join(validation['messages']), None
        
        # File is valid, return the data
        return True, "File read successfully", validation['data']
        
    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        return False, f"Error reading file: {str(e)}", None