#!/usr/bin/env python3
"""
Script to clear the risk analysis cache.
"""

from backend import db
from backend.app import create_app
from backend.models import RiskAnalysisCache

def clear_cache():
    """Clear the risk analysis cache"""
    app = create_app()
    with app.app_context():
        try:
            db.session.query(RiskAnalysisCache).delete()
            db.session.commit()
            print("Cleared all risk analysis cache")
            return True
        except Exception as e:
            print(f"Error clearing cache: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    clear_cache()
