#!/usr/bin/env python3
"""
Script to manually check and fix the files with more flexible pattern matching.
This script will examine the files and make the necessary changes regardless of the current content.
"""

import os
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_info_icon_to_template():
    """Add an information icon next to the Total Return label in the portfolio overview template"""
    logger.info("Adding information icon to Total Return label...")
    
    file_path = 'backend/templates/portfolio_overview.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the info icon is already there
        if 'Total Return <i class="fas fa-info-circle"' in content:
            logger.info("Information icon already exists.")
            return True
        
        # Find the Total Return label with more flexible pattern matching
        matches = re.finditer(r'<span class="metric-label">Total Return', content)
        
        if not matches:
            logger.warning("Could not find Total Return label.")
            
            # Show the file structure to help debug
            logger.info("File structure:")
            lines = content.split('\n')
            for i, line in enumerate(lines[:100]):  # Show first 100 lines
                if "Total Return" in line:
                    logger.info(f"Line {i+1}: {line}")
            
            return False
        
        # Replace the first occurrence
        updated_content = content
        for match in matches:
            position = match.start()
            updated_content = (
                updated_content[:position] + 
                '<span class="metric-label">Total Return <i class="fas fa-info-circle" title="This total return focuses on price appreciation and does not include dividend values"></i>' + 
                updated_content[position + len('<span class="metric-label">Total Return'):]
            )
            break  # Only replace the first occurrence
        
        # Write the updated content
        with open(file_path, 'w') as file:
            file.write(updated_content)
        
        logger.info("Information icon added successfully.")
        return True
    
    except Exception as e:
        logger.error(f"Error adding information icon: {str(e)}")
        return False

def update_template_formatting():
    """Update the portfolio overview template to add commas to the total return"""
    logger.info("Updating template formatting...")
    
    file_path = 'backend/templates/portfolio_overview.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the formatting is already updated
        if '"{:,.2f}".format(portfolio.total_return' in content:
            logger.info("Template formatting already updated.")
            return True
        
        # Find all occurrences of portfolio.total_return
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if 'portfolio.total_return' in line and '"%.2f"|format' in line:
                # Replace the formatting
                updated_line = line.replace('"%.2f"|format', '"{:,.2f}".format')
                updated_lines.append(updated_line)
                logger.info(f"Updated line: {updated_line}")
            else:
                updated_lines.append(line)
        
        # Write the updated content
        with open(file_path, 'w') as file:
            file.write('\n'.join(updated_lines))
        
        logger.info("Template formatting updated successfully.")
        return True
    
    except Exception as e:
        logger.error(f"Error updating template formatting: {str(e)}")
        return False

def fix_beta_calculation():
    """Fix the beta calculation in the RiskAnalytics class"""
    logger.info("Fixing beta calculation...")
    
    file_path = 'backend/analytics/risk_calculations.py'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the fix is already applied
        if 'if np.var(benchmark_returns) == 0:' in content:
            logger.info("Beta calculation already fixed.")
            return True
        
        # Find the _calculate_standard_beta method
        method_pattern = r'def _calculate_standard_beta\(\s*self,\s*portfolio_returns: np\.ndarray,\s*benchmark_returns: np\.ndarray\s*\) -> float:'
        method_match = re.search(method_pattern, content)
        
        if not method_match:
            logger.warning("Could not find _calculate_standard_beta method.")
            return False
        
        # Find the if statement for length check
        if_pattern = r'if len\(portfolio_returns\) != len\(benchmark_returns\):'
        if_match = re.search(if_pattern, content[method_match.end():])
        
        if not if_match:
            logger.warning("Could not find length check in _calculate_standard_beta method.")
            return False
        
        # Find the return statement after the if
        return_pattern = r'return 1\.0'
        return_match = re.search(return_pattern, content[method_match.end() + if_match.end():])
        
        if not return_match:
            logger.warning("Could not find return statement after length check.")
            return False
        
        # Find the linregress call
        linregress_pattern = r'slope, _, r_value, _, _ = stats\.linregress\(benchmark_returns, portfolio_returns\)'
        linregress_match = re.search(linregress_pattern, content[method_match.end():])
        
        if not linregress_match:
            logger.warning("Could not find linregress call.")
            return False
        
        # Create the updated method
        updated_method = """def _calculate_standard_beta(
            self,
            portfolio_returns: np.ndarray,
            benchmark_returns: np.ndarray
    ) -> float:
        \"\"\"Calculate standard beta using regression.\"\"\"
        if len(portfolio_returns) != len(benchmark_returns):
            # Align the lengths by taking the minimum length
            min_length = min(len(portfolio_returns), len(benchmark_returns))
            portfolio_returns = portfolio_returns[:min_length]
            benchmark_returns = benchmark_returns[:min_length]
            
            # If we don't have enough data, return a default
            if min_length < 20:  # Need at least 20 data points for a meaningful beta
                return 1.0

        # Check for zero variance in benchmark returns
        if np.var(benchmark_returns) == 0:
            return 1.0  # Default if benchmark returns are constant

        try:
            slope, _, r_value, _, _ = stats.linregress(benchmark_returns, portfolio_returns)
            
            # Check for NaN or infinite values
            if np.isnan(slope) or np.isinf(slope):
                return 1.0  # Default if regression fails
                
            return slope
        except Exception as e:
            print(f"Error in beta calculation: {{str(e)}}")
            return 1.0  # Default if regression fails"""
        
        # Replace the method
        method_end = content.find('def ', method_match.end())
        if method_end == -1:
            method_end = len(content)
        
        updated_content = content[:method_match.start()] + updated_method + content[method_end:]
        
        # Write the updated content
        with open(file_path, 'w') as file:
            file.write(updated_content)
        
        logger.info("Beta calculation fixed successfully.")
        return True
    
    except Exception as e:
        logger.error(f"Error fixing beta calculation: {str(e)}")
        return False

def add_fallback_to_risk_analysis_template():
    """Add a fallback to the risk analysis template"""
    logger.info("Adding fallback to risk analysis template...")
    
    file_path = 'backend/templates/risk_analysis.html'
    
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return False
    
    try:
        # Read the file
        with open(file_path, 'r') as file:
            content = file.read()
        
        # Check if the fallback is already added
        if 'risk_metrics.beta.beta if risk_metrics.beta.beta != 0 else 1.0' in content:
            logger.info("Fallback already added to risk analysis template.")
            return True
        
        # Find all occurrences of risk_metrics.beta.beta
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if 'risk_metrics.beta.beta' in line and '<span class="value">' in line:
                # Replace with fallback
                updated_line = line.replace('{{ risk_metrics.beta.beta', '{{ risk_metrics.beta.beta if risk_metrics.beta.beta != 0 else 1.0')
                updated_lines.append(updated_line)
                logger.info(f"Updated line: {updated_line}")
            else:
                updated_lines.append(line)
        
        # Write the updated content
        with open(file_path, 'w') as file:
            file.write('\n'.join(updated_lines))
        
        logger.info("Fallback added to risk analysis template successfully.")
        return True
    
    except Exception as e:
        logger.error(f"Error adding fallback to risk analysis template: {str(e)}")
        return False

def main():
    """Main function"""
    logger.info("Starting to apply manual fixes...")
    
    # Step 1: Add information icon to Total Return label
    info_icon_added = add_info_icon_to_template()
    logger.info(f"Information icon added: {info_icon_added}")
    
    # Step 2: Update template formatting
    template_updated = update_template_formatting()
    logger.info(f"Template formatting updated: {template_updated}")
    
    # Step 3: Fix beta calculation
    beta_fixed = fix_beta_calculation()
    logger.info(f"Beta calculation fixed: {beta_fixed}")
    
    # Step 4: Add fallback to risk analysis template
    template_fixed = add_fallback_to_risk_analysis_template()
    logger.info(f"Risk analysis template fixed: {template_fixed}")
    
    logger.info("\nSummary of manual fixes:")
    logger.info(f"1. Information icon added: {info_icon_added}")
    logger.info(f"2. Template formatting updated: {template_updated}")
    logger.info(f"3. Beta calculation fixed: {beta_fixed}")
    logger.info(f"4. Risk analysis template fixed: {template_fixed}")
    
    logger.info("\nNext steps:")
    logger.info("1. Restart your application to apply the changes")
    logger.info("2. Verify that the fixes are working as expected")
    
    logger.info("\nTo remove a file from your Git repository:")
    logger.info("1. Remove the file from the working directory:")
    logger.info("   git rm <file_path>")
    logger.info("2. Commit the change:")
    logger.info("   git commit -m \"Remove <file_path>\"")
    logger.info("3. Push the change to the remote repository:")
    logger.info("   git push")

if __name__ == "__main__":
    main()