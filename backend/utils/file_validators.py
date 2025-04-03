"""
File validation utilities for secure file uploads
"""
import os
import magic
import hashlib
from typing import Tuple, List, Dict, Any, Optional
from werkzeug.datastructures import FileStorage


def validate_file_security(file: FileStorage) -> Tuple[bool, str]:
    """
    Perform security validation on an uploaded file
    
    Args:
        file: The uploaded file object
        
    Returns:
        Tuple of (is_valid, message)
    """
    # Check if file is empty
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size == 0:
        return False, "File is empty"
    
    # Check file size (limit to 10MB)
    if file_size > 10 * 1024 * 1024:
        return False, "File too large. Maximum size is 10MB."
    
    # Validate file extension
    filename = file.filename
    file_ext = os.path.splitext(filename)[1].lower() if filename else ''
    
    allowed_extensions = ['.csv', '.xlsx', '.xls', '.txt']
    if file_ext not in allowed_extensions:
        return False, f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
    
    # Validate file content type using magic library
    try:
        # Read a sample of the file to detect its type
        file_sample = file.read(2048)
        file.seek(0)  # Reset file pointer
        
        # Use python-magic to detect file type
        mime = magic.Magic(mime=True)
        content_type = mime.from_buffer(file_sample)
        
        # Define allowed MIME types
        allowed_mime_types = {
            '.csv': ['text/csv', 'text/plain'],
            '.txt': ['text/plain'],
            '.xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
                     'application/vnd.ms-excel'],
            '.xls': ['application/vnd.ms-excel']
        }
        
        if content_type not in allowed_mime_types.get(file_ext, []):
            return False, f"File content doesn't match its extension. Detected: {content_type}"
        
    except Exception as e:
        return False, f"Error validating file content: {str(e)}"
    
    # Calculate file hash for logging/tracking
    file_hash = calculate_file_hash(file)
    file.seek(0)  # Reset file pointer
    
    return True, "File passed security validation"


def calculate_file_hash(file: FileStorage) -> str:
    """
    Calculate SHA-256 hash of file contents
    
    Args:
        file: The file object
        
    Returns:
        Hash string
    """
    file.seek(0)
    file_hash = hashlib.sha256()
    
    # Read and update hash in chunks to avoid loading large files into memory
    for chunk in iter(lambda: file.read(4096), b""):
        file_hash.update(chunk)
    
    file.seek(0)  # Reset file pointer
    return file_hash.hexdigest()


def sanitize_file_content(file: FileStorage, file_ext: str) -> Tuple[bool, str, Any]:
    """
    Sanitize file content to prevent security issues
    
    Args:
        file: The file object
        file_ext: File extension
        
    Returns:
        Tuple of (success, message, sanitized_content)
    """
    try:
        # Implement content sanitization based on file type
        # For CSV/TXT: Check for dangerous content, macros, etc.
        # For Excel: Disable macros, formulas, etc.
        
        # This is a placeholder for actual implementation
        return True, "File content sanitized", file
        
    except Exception as e:
        return False, f"Error sanitizing file: {str(e)}", None