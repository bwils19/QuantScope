import os
from datetime import datetime

from backend import db
from backend.models import SecurityMetadata, Security
from backend.services.market.api_client import AlphaVantageClient, logger


class SecurityMetadataService:
    def __init__(self):
        self.api_client = AlphaVantageClient(os.getenv('ALPHA_VANTAGE_KEY'))

    def update_security_metadata(self, ticker):
        """Update metadata for a single security"""
        try:
            # Check if we already have recent metadata
            existing = SecurityMetadata.query.filter_by(ticker=ticker).first()
            if existing and (datetime.utcnow() - existing.last_updated).days < 30:
                # Skip if metadata is less than 30 days old, no need to keep getting this as it rarely changes
                return True

            overview_data = self.api_client.fetch_security_overview(ticker)
            if not overview_data:
                return False

            if existing:
                # Update existing record
                for key, value in overview_data.items():
                    setattr(existing, key, value)
            else:
                # Create new record
                metadata = SecurityMetadata(**overview_data)
                db.session.add(metadata)

            db.session.commit()
            return True

        except Exception as e:
            logger.error(f"Error updating metadata for {ticker}: {str(e)}")
            db.session.rollback()
            return False

    def bulk_update_metadata(self):
        """Update metadata for all securities in portfolios"""
        try:
            # Get all unique tickers from securities table
            tickers = db.session.query(Security.ticker).distinct().all()
            tickers = [t[0] for t in tickers]

            updated_count = 0
            for ticker in tickers:
                if self.update_security_metadata(ticker):
                    updated_count += 1

            return {
                'success': True,
                'tickers_updated': updated_count,
                'total_tickers': len(tickers)
            }

        except Exception as e:
            logger.error(f"Error in bulk metadata update: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }