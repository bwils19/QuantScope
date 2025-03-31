#!/usr/bin/env python3
"""
Script to run all remaining fix scripts in sequence.
This will:
1. Fix portfolio view synchronization
2. Fix beta calculation and formatting issues
3. Implement fixes for beta calculation and formatting
4. Add information icon to Total Return label
5. Fix beta value showing as 0.0
6. Implement beta value fix
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
    logger.info("Starting to run remaining fix scripts...")
    
    # Step 1: Analyze and fix portfolio view synchronization
    if run_script("fix_portfolio_view_sync.py"):
        logger.info("Successfully analyzed portfolio view synchronization")
    else:
        logger.error("Failed to analyze portfolio view synchronization")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 2: Fix beta calculation and formatting issues
    if run_script("fix_beta_calculation.py"):
        logger.info("Successfully analyzed beta calculation and formatting issues")
    else:
        logger.error("Failed to analyze beta calculation and formatting issues")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 3: Implement fixes for beta calculation and formatting
    if run_script("implement_fixes.py"):
        logger.info("Successfully implemented fixes for beta calculation and formatting")
    else:
        logger.error("Failed to implement fixes for beta calculation and formatting")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 4: Add information icon to Total Return label
    if run_script("add_info_icon.py"):
        logger.info("Successfully added information icon to Total Return label")
    else:
        logger.error("Failed to add information icon to Total Return label")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 5: Fix beta value showing as 0.0
    if run_script("fix_beta_value.py"):
        logger.info("Successfully analyzed beta value issue")
    else:
        logger.error("Failed to analyze beta value issue")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 6: Implement beta value fix
    if run_script("implement_beta_fix.py"):
        logger.info("Successfully implemented beta value fix")
    else:
        logger.error("Failed to implement beta value fix")
        if not input("Continue anyway? (y/n): ").lower().startswith('y'):
            return
    
    # Step 7: Show instructions for fixing the upload function
    logger.info("Showing instructions for fixing the upload function...")
    run_script("fix_upload_function.py")
    
    logger.info("All fix scripts have been run")
    logger.info("Please check the README_FIX_DAY_CHANGE.md file for more information")

if __name__ == "__main__":
    main()