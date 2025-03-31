#!/usr/bin/env python3
"""
Script to check if the fixes have been applied correctly.
This script will examine the files and report whether the fixes are present.
"""

import os
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_info_icon():
    """Check if the information icon is present in the portfolio overview template"""
    logger.info("Checking information icon...")
    
    file_path = 'backend/templates/portfolio_overview.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the info icon is present
        if 'Total Return <i class="fas fa-info-circle"' in content:
            logger.info("Information icon is present.")
            
            # Show the line with the icon
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'Total Return <i class="fas fa-info-circle"' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return True
        else:
            logger.warning("Information icon is not present.")
            
            # Show the lines with Total Return
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'Total Return' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return False
    
    except Exception as e:
        logger.error(f"Error checking information icon: {str(e)}")
        return False

def check_template_formatting():
    """Check if the template formatting has been updated"""
    logger.info("Checking template formatting...")
    
    file_path = 'backend/templates/portfolio_overview.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the formatting is updated
        if '"{:,.2f}".format(portfolio.total_return' in content:
            logger.info("Template formatting is updated.")
            
            # Show the line with the formatting
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if '"{:,.2f}".format(portfolio.total_return' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return True
        else:
            logger.warning("Template formatting is not updated.")
            
            # Show the lines with total_return
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'portfolio.total_return' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return False
    
    except Exception as e:
        logger.error(f"Error checking template formatting: {str(e)}")
        return False

def check_beta_calculation():
    """Check if the beta calculation has been fixed"""
    logger.info("Checking beta calculation...")
    
    file_path = 'backend/analytics/risk_calculations.py'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the fix is applied
        if 'if np.var(benchmark_returns) == 0:' in content:
            logger.info("Beta calculation is fixed.")
            
            # Show the relevant part of the method
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'if np.var(benchmark_returns) == 0:' in line:
                    logger.info(f"Line {i+1}: {line}")
                    # Show a few lines before and after
                    for j in range(max(0, i-5), min(len(lines), i+5)):
                        logger.info(f"Line {j+1}: {lines[j]}")
            
            return True
        else:
            logger.warning("Beta calculation is not fixed.")
            
            # Show the _calculate_standard_beta method
            lines = content.split('\n')
            in_method = False
            for i, line in enumerate(lines):
                if 'def _calculate_standard_beta' in line:
                    in_method = True
                    logger.info(f"Line {i+1}: {line}")
                elif in_method and 'def ' in line:
                    in_method = False
                elif in_method:
                    logger.info(f"Line {i+1}: {line}")
            
            return False
    
    except Exception as e:
        logger.error(f"Error checking beta calculation: {str(e)}")
        return False

def check_risk_analysis_template():
    """Check if the fallback has been added to the risk analysis template"""
    logger.info("Checking risk analysis template...")
    
    file_path = 'backend/templates/risk_analysis.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the fallback is added
        if 'risk_metrics.beta.beta if risk_metrics.beta.beta != 0 else 1.0' in content:
            logger.info("Fallback is added to risk analysis template.")
            
            # Show the line with the fallback
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'risk_metrics.beta.beta if risk_metrics.beta.beta != 0 else 1.0' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return True
        else:
            logger.warning("Fallback is not added to risk analysis template.")
            
            # Show the lines with risk_metrics.beta.beta
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'risk_metrics.beta.beta' in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return False
    
    except Exception as e:
        logger.error(f"Error checking risk analysis template: {str(e)}")
        return False

def main():
    """Main function"""
    logger.info("Starting to check fixes...")
    
    # Step 1: Check information icon
    info_icon_present = check_info_icon()
    logger.info(f"Information icon present: {info_icon_present}")
    
    # Step 2: Check template formatting
    template_updated = check_template_formatting()
    logger.info(f"Template formatting updated: {template_updated}")
    
    # Step 3: Check beta calculation
    beta_fixed = check_beta_calculation()
    logger.info(f"Beta calculation fixed: {beta_fixed}")
    
    # Step 4: Check risk analysis template
    template_fixed = check_risk_analysis_template()
    logger.info(f"Risk analysis template fixed: {template_fixed}")
    
    logger.info("\nSummary of checks:")
    logger.info(f"1. Information icon present: {info_icon_present}")
    logger.info(f"2. Template formatting updated: {template_updated}")
    logger.info(f"3. Beta calculation fixed: {beta_fixed}")
    logger.info(f"4. Risk analysis template fixed: {template_fixed}")
    
    if info_icon_present and template_updated and beta_fixed and template_fixed:
        logger.info("\nAll fixes have been applied correctly!")
    else:
        logger.warning("\nSome fixes have not been applied correctly.")
        
        if not info_icon_present:
            logger.info("\nTo add the information icon manually:")
            logger.info("1. Open backend/templates/portfolio_overview.html")
            logger.info("2. Find the line with '<span class=\"metric-label\">Total Return</span>'")
            logger.info("3. Replace it with '<span class=\"metric-label\">Total Return <i class=\"fas fa-info-circle\" title=\"This total return focuses on price appreciation and does not include dividend values\"></i></span>'")
        
        if not template_updated:
            logger.info("\nTo update the template formatting manually:")
            logger.info("1. Open backend/templates/portfolio_overview.html")
            logger.info("2. Find the line with '${{ \"%.2f\"|format(portfolio.total_return|default(0)) }}'")
            logger.info("3. Replace it with '${{ \"{:,.2f}\".format(portfolio.total_return|default(0)) }}'")
        
        if not beta_fixed:
            logger.info("\nTo fix the beta calculation manually:")
            logger.info("1. Open backend/analytics/risk_calculations.py")
            logger.info("2. Find the _calculate_standard_beta method")
            logger.info("3. Replace it with the improved version that handles edge cases")
        
        if not template_fixed:
            logger.info("\nTo add the fallback to the risk analysis template manually:")
            logger.info("1. Open backend/templates/risk_analysis.html")
            logger.info("2. Find the lines with 'risk_metrics.beta.beta'")
            logger.info("3. Replace them with 'risk_metrics.beta.beta if risk_metrics.beta.beta != 0 else 1.0'")

if __name__ == "__main__":
    main()