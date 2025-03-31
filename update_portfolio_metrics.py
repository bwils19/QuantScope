#!/usr/bin/env python3
"""
Script to update all portfolio metrics after securities have been updated.
This will recalculate day change values for all portfolios.
"""

import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import after environment variables are loaded
from backend import db
from backend.app import create_app  # Correct import for create_app
from backend.models import Portfolio, PortfolioSecurity, Security

def update_portfolio_metrics_directly(portfolio_id):
    """Update portfolio metrics directly without using PriceUpdateService"""
    try:
        # Get the portfolio
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            logger.warning(f"Portfolio {portfolio_id} not found")
            return {"success": False, "error": "Portfolio not found"}

        # Get all portfolio securities with joined security data
        portfolio_securities = (
            db.session.query(PortfolioSecurity, Security)
            .join(Security, PortfolioSecurity.security_id == Security.id)
            .filter(PortfolioSecurity.portfolio_id == portfolio_id)
            .all()
        )

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
        total_return = 0
        total_return_pct = 0
        
        if total_cost_basis > 0:
            total_return = total_value - total_cost_basis
            total_return_pct = (total_value / total_cost_basis - 1) * 100
        
        portfolio.total_return = total_return
        portfolio.total_return_pct = total_return_pct
        
        portfolio.updated_at = datetime.utcnow()
        
        # Commit changes
        db.session.commit()
        
        logger.info(f"Portfolio {portfolio_id} metrics updated successfully")
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "total_value": total_value,
            "day_change": day_change,
            "total_gain": total_gain
        }
    
    except Exception as e:
        logger.error(f"Error updating portfolio metrics: {str(e)}", exc_info=True)
        db.session.rollback()
        return {
            "success": False,
            "error": str(e)
        }

def main():
    """Main function to update all portfolio metrics"""
    app = create_app()
    with app.app_context():
        # Get all portfolios
        portfolios = Portfolio.query.all()
        logger.info(f"Found {len(portfolios)} portfolios to update")
        
        # Process each portfolio
        success_count = 0
        error_count = 0
        
        for i, portfolio in enumerate(portfolios):
            try:
                logger.info(f"Processing {i+1}/{len(portfolios)}: {portfolio.name} (ID: {portfolio.id})")
                
                # Update portfolio metrics directly
                result = update_portfolio_metrics_directly(portfolio.id)
                
                if result.get('success', False):
                    success_count += 1
                    logger.info(f"Successfully updated metrics for portfolio {portfolio.id}")
                    logger.info(f"  Total value: ${result.get('total_value', 0):.2f}")
                    logger.info(f"  Day change: ${result.get('day_change', 0):.2f}")
                    logger.info(f"  Total gain: ${result.get('total_gain', 0):.2f}")
                else:
                    error_count += 1
                    logger.error(f"Failed to update metrics for portfolio {portfolio.id}: {result.get('error', 'Unknown error')}")
                
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing portfolio {portfolio.id}: {str(e)}")
        
        logger.info(f"Completed processing {len(portfolios)} portfolios")
        logger.info(f"Success: {success_count}, Errors: {error_count}")

if __name__ == "__main__":
    main()