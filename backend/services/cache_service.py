from datetime import datetime, timedelta
from typing import Dict, Any
from backend import db
from backend.models import Portfolio

# Cache storage
risk_cache: Dict[str, Any] = {}


def invalidate_portfolio_cache(portfolio_id: int) -> None:
    """Invalidate cached risk data for a specific portfolio"""
    cache_key = f"risk_{portfolio_id}"
    if cache_key in risk_cache:
        del risk_cache[cache_key]


def invalidate_user_cache(user_id: int) -> None:
    """Invalidate all cached risk data for a user's portfolios"""
    portfolios = Portfolio.query.filter_by(user_id=user_id).all()
    for portfolio in portfolios:
        invalidate_portfolio_cache(portfolio.id)


def get_cached_risk_components(portfolio_id: int, securities_data):
    """Get risk components from cache or calculate if needed"""
    cache_key = f"risk_{portfolio_id}"

    if cache_key in risk_cache:
        cached_data = risk_cache[cache_key]
        cache_time = cached_data['timestamp']
        if datetime.now() - cache_time < timedelta(minutes=5):
            return cached_data['components']

    from backend.analytics.risk_calculations import RiskAnalytics
    risk_analyzer = RiskAnalytics()
    var_components = risk_analyzer.get_var_components(securities_data)

    risk_cache[cache_key] = {
        'components': var_components,
        'timestamp': datetime.now()
    }

    return var_components
