#!/usr/bin/env python3
"""
Script to run all fix scripts in sequence.
This will:
1. Fix securities with complete information from Alpha Vantage API
2. Fix missing company names
3. Fix previous_close values using historical data
4. Update all portfolio metrics
"""

import os
import sys
import logging
import subprocess
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_script(script_name):
    """Run a Python script and return the result"""
    logger.info(f"Running {script_name}...")
    
    try:
        result = subprocess.run(
            [sys.executable, script_name],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"{script_name} completed successfully")
        logger.info(f"Output: {result.stdout}")
        return True
    
    except subprocess.CalledProcessError as e:
        logger.error(f"{script_name} failed with error code {e.returncode}")
        logger.error(f"Error output: {e.stderr}")
        return False

def main():
    """Main function to run all fix scripts"""
    logger.info("Starting to run all fix scripts...")
    
    # Step 1: Fix securities with complete information
    if run_script("fix_zero_prices.py"):
        logger.info("Successfully updated securities with complete information")
    else:
        logger.error("Failed to update securities with complete information")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 2: Fix missing company names
    if run_script("fix_missing_names.py"):
        logger.info("Successfully fixed missing company names")
    else:
        logger.error("Failed to fix missing company names")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 3: Fix previous_close values
    if run_script("fix_previous_close.py"):
        logger.info("Successfully fixed previous_close values")
    else:
        logger.error("Failed to fix previous_close values")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 4: Update portfolio metrics
    if run_script("update_portfolio_metrics.py"):
        logger.info("Successfully updated portfolio metrics")
    else:
        logger.error("Failed to update portfolio metrics")
    
    # Step 5: Show instructions for fixing the upload function
    logger.info("Showing instructions for fixing the upload function...")
    run_script("fix_upload_function.py")
    
    logger.info("All fix scripts have been run")
    logger.info("Please check the README_FIX_DAY_CHANGE.md file for more information")

if __name__ == "__main__":
    main()