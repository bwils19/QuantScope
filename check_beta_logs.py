#!/usr/bin/env python3
"""
Script to check the logs for beta calculation debugging information.
Run this on your Digital Ocean server after viewing the risk analysis page.
"""

import os
import re
import sys
import subprocess

def check_logs():
    """Check the logs for beta calculation debugging information"""
    print("Checking logs for beta calculation debugging information...")
    
    # Try different log files
    log_files = [
        '/root/QuantScope/logs/app.log',
        '/var/log/quantscope.log',
        '/var/log/syslog'
    ]
    
    for log_file in log_files:
        if os.path.exists(log_file):
            print(f"\nChecking log file: {log_file}")
            
            # Use grep to find beta calculation debugging information
            try:
                result = subprocess.run(
                    ['grep', '-A', '50', 'DEBUG: _calculate_standard_beta', log_file],
                    capture_output=True,
                    text=True
                )
                
                if result.stdout:
                    print("\nFound beta calculation debugging information:")
                    print(result.stdout)
                else:
                    print("No beta calculation debugging information found in this log file.")
                    
                    # Try to find any beta-related information
                    result = subprocess.run(
                        ['grep', '-A', '10', 'beta', log_file],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.stdout:
                        print("\nFound beta-related information:")
                        print(result.stdout)
                    else:
                        print("No beta-related information found in this log file.")
            except Exception as e:
                print(f"Error checking log file: {str(e)}")
        else:
            print(f"\nLog file not found: {log_file}")
    
    # Check the application output
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'quantscope.service', '-n', '1000'],
            capture_output=True,
            text=True
        )
        
        if result.stdout:
            print("\nChecking application output:")
            
            # Look for beta calculation debugging information
            beta_debug = re.findall(r'DEBUG: _calculate_standard_beta.*?SUCCESS|ERROR', result.stdout, re.DOTALL)
            
            if beta_debug:
                print("\nFound beta calculation debugging information:")
                for debug in beta_debug:
                    print(debug)
            else:
                print("No beta calculation debugging information found in application output.")
                
                # Look for any beta-related information
                beta_info = re.findall(r'[Bb]eta.*', result.stdout)
                
                if beta_info:
                    print("\nFound beta-related information:")
                    for info in beta_info:
                        print(info)
                else:
                    print("No beta-related information found in application output.")
        else:
            print("\nNo application output found.")
    except Exception as e:
        print(f"Error checking application output: {str(e)}")

if __name__ == "__main__":
    check_logs()
