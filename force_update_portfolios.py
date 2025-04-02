#!/usr/bin/env python3
"""
Script to force update all portfolios with correct DAY CHANGE and TOTAL RETURN values.
This script directly updates the database to ensure the values are displayed correctly
on the portfolio cards on the portfolio-overview page.
"""

import os
import sys
import logging
from datetime import datetime
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add the current directory to the path so we can import the app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def main():
    """Force update all portfolios"""
    logger.info("Starting portfolio force update...")
    
    try:
        # Import the app and models
        from backend import create_app, db
        from backend.models import Portfolio, PortfolioSecurity, Security
        from sqlalchemy import func
        
        # Create the app context
        app = create_app()
        
        with app.app_context():
            # Get all portfolios
            portfolios = Portfolio.query.all()
            logger.info(f"Found {len(portfolios)} portfolios to update")
            
            success_count = 0
            error_count = 0
            
            for portfolio in portfolios:
                try:
                    logger.info(f"Updating portfolio {portfolio.id}: {portfolio.name}")
                    
                    # Get all portfolio securities with joined security data
                    portfolio_securities = (
                        db.session.query(PortfolioSecurity, Security)
                        .join(Security, PortfolioSecurity.security_id == Security.id)
                        .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                        .all()
                    )
                    
                    if not portfolio_securities:
                        logger.warning(f"No securities found for portfolio {portfolio.id}")
                        continue
                    
                    # Track totals
                    total_value = 0
                    total_cost_basis = 0
                    day_change = 0
                    total_gain = 0
                    
                    for ps, security in portfolio_securities:
                        # Use consistent price data
                        current_price = security.current_price or 0
                        previous_close = security.previous_close or current_price
                        
                        # Calculate security metrics
                        security_value = ps.amount_owned * current_price
                        security_day_change = ps.amount_owned * (current_price - previous_close)
                        
                        # Update portfolio_security values
                        ps.total_value = security_value
                        ps.value_change = security_day_change
                        
                        # Calculate percentage changes only if denominators are non-zero
                        prev_day_value = ps.amount_owned * previous_close
                        if prev_day_value > 0:
                            ps.value_change_pct = (security_day_change / prev_day_value) * 100
                        else:
                            ps.value_change_pct = 0
                        
                        # Calculate gain/loss using purchase price
                        if ps.purchase_price and ps.purchase_price > 0:
                            security_cost = ps.amount_owned * ps.purchase_price
                            security_gain = security_value - security_cost
                            
                            ps.total_gain = security_gain
                            ps.total_gain_pct = (security_gain / security_cost) * 100 if security_cost > 0 else 0
                            
                            # Add to portfolio totals
                            total_cost_basis += security_cost
                            total_gain += security_gain
                        else:
                            ps.total_gain = 0
                            ps.total_gain_pct = 0
                        
                        # Add to portfolio totals
                        total_value += security_value
                        day_change += security_day_change
                    
                    # Update portfolio totals
                    portfolio.total_value = total_value
                    portfolio.day_change = day_change
                    
                    # Calculate percentage changes for portfolio
                    day_base = total_value - day_change
                    if day_base > 0:
                        portfolio.day_change_pct = (day_change / day_base) * 100
                    else:
                        portfolio.day_change_pct = 0
                    
                    portfolio.total_gain = total_gain
                    if total_cost_basis > 0:
                        portfolio.total_gain_pct = (total_gain / total_cost_basis) * 100
                    else:
                        portfolio.total_gain_pct = 0
                    
                    # Calculate total return
                    initial_value = sum(
                        ps.purchase_price * ps.amount_owned
                        for ps, _ in portfolio_securities
                        if ps.purchase_price is not None and ps.purchase_price > 0
                    )
                    
                    if initial_value > 0:
                        # Calculate return
                        absolute_return = total_value - initial_value
                        percent_return = (total_value / initial_value - 1) * 100
                        
                        # Update portfolio
                        portfolio.total_return = absolute_return
                        portfolio.total_return_pct = percent_return
                        
                        logger.info(f"Portfolio {portfolio.id}: Total return: ${absolute_return} ({percent_return:.2f}%)")
                    else:
                        logger.warning(f"Portfolio {portfolio.id}: No valid initial value found, setting total return to 0")
                        portfolio.total_return = 0
                        portfolio.total_return_pct = 0
                    
                    portfolio.updated_at = datetime.utcnow()
                    
                    # Log the updated values
                    logger.info(f"Portfolio {portfolio.id} updated:")
                    logger.info(f"  Total value: ${portfolio.total_value}")
                    logger.info(f"  Day change: ${portfolio.day_change} ({portfolio.day_change_pct:.2f}%)")
                    logger.info(f"  Total gain: ${portfolio.total_gain} ({portfolio.total_gain_pct:.2f}%)")
                    logger.info(f"  Total return: ${portfolio.total_return} ({portfolio.total_return_pct:.2f}%)")
                    
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Error updating portfolio {portfolio.id}: {str(e)}")
                    logger.error(traceback.format_exc())
                    error_count += 1
            
            # Commit all changes
            db.session.commit()
            
            logger.info(f"Portfolio update complete. Success: {success_count}, Errors: {error_count}")
    
    except Exception as e:
        logger.error(f"Error in force update: {str(e)}")
        logger.error(traceback.format_exc())
    
    logger.info("Portfolio force update complete")

if __name__ == "__main__":
    main()
