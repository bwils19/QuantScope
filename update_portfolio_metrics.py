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
from backend import db, create_app
from backend.models import Portfolio, PortfolioSecurity, Security
from backend.services.price_update_service import PriceUpdateService

def main():
    """Main function to update all portfolio metrics"""
    app = create_app()
    with app.app_context():
        # Create price update service
        price_service = PriceUpdateService()
        
        # Get all portfolios
        portfolios = Portfolio.query.all()
        logger.info(f"Found {len(portfolios)} portfolios to update")
        
        # Process each portfolio
        success_count = 0
        error_count = 0
        
        for i, portfolio in enumerate(portfolios):
            try:
                logger.info(f"Processing {i+1}/{len(portfolios)}: {portfolio.name} (ID: {portfolio.id})")
                
                # Update portfolio metrics
                result = price_service.update_portfolio_metrics(portfolio.id)
                
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