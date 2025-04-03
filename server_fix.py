#!/usr/bin/env python3
"""
Script to fix the total return calculation and recalculate portfolio metrics.
This script should be run directly on the server.
"""
import os
import sys
from datetime import datetime

def main():
    print(f"Starting portfolio fix at {datetime.now()}")
    
    # Import Flask app and database
    from backend.app import create_app
    from backend import db
    from backend.models import Portfolio, PortfolioSecurity
    
    # Create Flask app context
    app = create_app()
    with app.app_context():
        print("Recalculating metrics for all portfolios...")
        
        try:
            # Get all portfolios
            portfolios = db.session.query(Portfolio).all()
            print(f"Found {len(portfolios)} portfolios to update")
            
            success_count = 0
            error_count = 0
            
            for portfolio in portfolios:
                try:
                    # Get current portfolio value
                    current_value = portfolio.total_value
                    
                    # Get portfolio securities
                    portfolio_securities = db.session.query(PortfolioSecurity).filter_by(
                        portfolio_id=portfolio.id
                    ).all()
                    
                    # Calculate initial value
                    initial_value = sum(
                        ps.purchase_price * ps.amount_owned
                        for ps in portfolio_securities
                        if ps.purchase_price is not None and ps.purchase_price > 0
                    )
                    
                    print(f"Portfolio {portfolio.id}: Current value: ${current_value}, Initial value: ${initial_value}")
                    
                    if initial_value > 0:
                        # Calculate return
                        absolute_return = current_value - initial_value
                        percent_return = (current_value / initial_value - 1) * 100
                        
                        # Update portfolio
                        portfolio.total_return = absolute_return
                        portfolio.total_return_pct = percent_return
                        
                        print(f"Portfolio {portfolio.id}: Total return: ${absolute_return} ({percent_return:.2f}%)")
                    else:
                        # Use total_gain as a fallback
                        total_gain = portfolio.total_gain
                        
                        if total_gain is not None and total_gain != 0:
                            # Use total_gain for total_return
                            portfolio.total_return = total_gain
                            
                            # Calculate percentage based on current value
                            if current_value > 0:
                                portfolio.total_return_pct = (total_gain / (current_value - total_gain)) * 100
                            else:
                                portfolio.total_return_pct = 0
                                
                            print(f"Portfolio {portfolio.id}: Using total gain as total return: ${total_gain} ({portfolio.total_return_pct:.2f}%)")
                        else:
                            # If total_gain is also not available, set to 0
                            print(f"Portfolio {portfolio.id}: No valid total_gain found, setting total return to 0")
                            portfolio.total_return = 0
                            portfolio.total_return_pct = 0
                    
                    # Update the updated_at timestamp
                    portfolio.updated_at = datetime.utcnow()
                    
                    success_count += 1
                except Exception as e:
                    print(f"Error updating portfolio {portfolio.id}: {str(e)}")
                    error_count += 1
            
            # Commit changes
            db.session.commit()
            
            print(f"Portfolio metrics update complete. Success: {success_count}, Errors: {error_count}")
            return {
                'success': True,
                'total': len(portfolios),
                'success_count': success_count,
                'error_count': error_count
            }
        
        except Exception as e:
            print(f"Error recalculating portfolio metrics: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

if __name__ == "__main__":
    result = main()
    print(f"Recalculation result: {result}")