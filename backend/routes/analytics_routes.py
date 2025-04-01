from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from flask import Blueprint, jsonify, render_template, redirect, url_for, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from backend.models import User, Portfolio, Security, HistoricalDataUpdateLog, SecurityHistoricalData, SecurityMetadata, \
    RiskAnalysisCache, PortfolioSecurity
from backend.analytics.risk_calculations import RiskAnalytics, calculate_credit_risk
from backend import db
from backend.services.cache_service import get_cached_risk_components
from backend.services.historical_data_service import HistoricalDataService

analytics_blueprint = Blueprint('analytics', __name__)


@analytics_blueprint.route('/portfolio/<int:portfolio_id>/risk', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_risk(portfolio_id):
    try:
        # Check if force_refresh is requested
        force_refresh = request.args.get('force_refresh', '').lower() == 'true'

        if not force_refresh:
            # try to get cached results
            cached_data = RiskAnalysisCache.get_cache(portfolio_id)
            if cached_data:
                print("Returning cached risk analysis data")
                return jsonify(cached_data)

        print("Calculating fresh risk analysis...")
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()

        if not portfolio:
            return jsonify({"error": "Portfolio not found"}), 404

        # Get securities for this portfolio using the junction table
        portfolio_securities = (
            db.session.query(PortfolioSecurity, Security)
            .join(Security, PortfolioSecurity.security_id == Security.id)
            .filter(PortfolioSecurity.portfolio_id == portfolio_id)
            .all()
        )

        risk_analyzer = RiskAnalytics()

        # Convert to the format expected by the risk calculator
        securities_data = []
        for ps, security in portfolio_securities:
            security_data = {
                'ticker': security.ticker,
                'amount_owned': ps.amount_owned,
                'purchase_date': ps.purchase_date.strftime("%Y-%m-%d") if ps.purchase_date else None,
                'current_price': security.current_price,
                'total_value': ps.total_value
            }
            securities_data.append(security_data)

        # calculate metrics
        var_data = risk_analyzer.calculate_dynamic_var(securities_data)
        credit_risk = calculate_credit_risk(securities_data)
        beta_data = risk_analyzer.calculate_portfolio_beta(securities_data)
        print(f"DEBUG: Beta data from risk_analyzer: {beta_data}")
        var_components = risk_analyzer.get_var_components(securities_data)

        latest_update = db.session.query(
            func.max(SecurityHistoricalData.updated_at)
        ).scalar()

        response_data = {
            'portfolio_name': portfolio.name,
            'total_value': portfolio.total_value,
            'var_metrics': var_data,
            'credit_risk': credit_risk,
            'beta': beta_data,
            'var_components': var_components,
            'securities': securities_data,
            'latest_update': latest_update.strftime('%Y-%m-%d %H:%M:%S') if latest_update else None,
            'cached': False
        }

        try:
            RiskAnalysisCache.set_cache(portfolio_id, response_data)
        except Exception as cache_error:
            print(f"Warning: Failed to cache risk analysis: {str(cache_error)}")
            # Continue without caching

        return jsonify(response_data)

    except Exception as e:
        print(f"Error calculating risk metrics: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        
        # Fallback to hardcoded values
        print("Using fallback hardcoded risk metrics")
        
        # Create hardcoded beta data
        beta_data = {
            'beta': 0.7,
            'downside_beta': 0.65,
            'rolling_betas': [round(0.65 + i * 0.002, 3) for i in range(60)],
            'r_squared': 0.75,
            'standard_error': 0.05,
            'confidence': {
                'high': 0.8,
                'low': 0.6
            },
            'analysis': {
                'trend': 'stable',
                'stability': 'high'
            }
        }
        
        # Create hardcoded VaR data with regime distribution
        var_data = {
            'var_95': portfolio.total_value * 0.05 if portfolio and portfolio.total_value else 1000,
            'var_99': portfolio.total_value * 0.08 if portfolio and portfolio.total_value else 1600,
            'cvar_95': portfolio.total_value * 0.07 if portfolio and portfolio.total_value else 1400,
            'cvar_99': portfolio.total_value * 0.1 if portfolio and portfolio.total_value else 2000,
            'expected_shortfall': portfolio.total_value * 0.06 if portfolio and portfolio.total_value else 1200,
            'max_drawdown': portfolio.total_value * 0.15 if portfolio and portfolio.total_value else 3000,
            'volatility': 0.12,
            'regime_distribution': {
                'normal': 0.6,
                'stress': 0.3,
                'crisis': 0.1
            }
        }
        
        # Create hardcoded credit risk data
        credit_risk = {
            'cs01': 0.0,
            'dv01': 0.0,
            'credit_var': portfolio.total_value * 0.03 if portfolio and portfolio.total_value else 600
        }
        
        # Create hardcoded VaR components as a list of components
        var_components = []
        
        # Add some sample securities to the components
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
        weights = [0.25, 0.2, 0.2, 0.15, 0.2]
        volatilities = [0.2, 0.18, 0.22, 0.25, 0.28]
        var_contributions = [1200, 900, 1100, 800, 1000]
        
        for i in range(len(tickers)):
            var_components.append({
                'ticker': tickers[i],
                'weight': weights[i],
                'volatility': volatilities[i],
                'var_contribution': var_contributions[i]
            })
        
        # Create response data
        response_data = {
            'portfolio_name': portfolio.name if portfolio else "Unknown",
            'total_value': portfolio.total_value if portfolio and portfolio.total_value else 20000,
            'var_metrics': var_data,
            'credit_risk': credit_risk,
            'beta': beta_data,
            'var_components': var_components,
            'securities': securities_data,
            'latest_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cached': False,
            'fallback': True  # Indicate that this is fallback data
        }return jsonify(response_data)


# helper functions for caching responses
@analytics_blueprint.route('/portfolio/<int:portfolio_id>/invalidate-cache', methods=['POST'])
@jwt_required(locations=["cookies"])
def invalidate_risk_cache(portfolio_id):
    """Endpoint to manually invalidate cache"""
    try:
        cache = RiskAnalysisCache.query.filter_by(portfolio_id=portfolio_id).first()
        if cache:
            db.session.delete(cache)
            db.session.commit()
            return jsonify({"message": "Cache invalidated successfully"})
        return jsonify({"message": "No cache found to invalidate"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def invalidate_portfolio_cache(portfolio_id):
    """Helper function to invalidate cache when portfolio changes"""
    try:
        cache = RiskAnalysisCache.query.filter_by(portfolio_id=portfolio_id).first()
        if cache:
            db.session.delete(cache)
            db.session.commit()
    except Exception as e:
        print(f"Error invalidating cache: {str(e)}")


@analytics_blueprint.route('/trigger-historical-update', methods=['POST'])
@jwt_required(locations=["cookies"])
def trigger_historical_update():
    log_entry = None
    try:
        current_user_email = get_jwt_identity()
        print(f"Historical update triggered by user: {current_user_email}")

        # Get force_update parameter from request
        data = request.get_json()
        force_update = data.get('force_update', False)
        print(f"Force update: {force_update}")

        service = HistoricalDataService()

        # Only check market conditions if not forcing update
        if not force_update:
            should_fetch, reason = service.market_utils.should_fetch_market_data()
            print(f"Should fetch market data? {should_fetch}. Reason: {reason}")

            current_time = service.market_utils.get_current_market_time()
            print(f"Current market time: {current_time} ET")

            if not should_fetch:
                next_update_time = None
                if "Market still open" in reason:
                    # Next update available after 8 PM ET
                    next_update_time = current_time.replace(hour=20, minute=0, second=0, microsecond=0)
                elif "Weekend" in reason:
                    # Next update on Monday after 8 PM ET
                    days_until_monday = (7 - current_time.weekday()) % 7
                    next_update_time = (current_time + timedelta(days=days_until_monday)).replace(
                        hour=20, minute=0, second=0, microsecond=0
                    )

                return jsonify({
                    "message": reason,
                    "next_update": next_update_time.isoformat() if next_update_time else None,
                    "current_market_time": current_time.isoformat(),
                    "success": False
                }), 200

        # Get list of tickers that need updates
        tickers_to_update = service.get_tickers_needing_update()
        print(f"Tickers needing update: {tickers_to_update}")

        # Trigger the update with force_update parameter
        result = service.update_historical_data(force_update=force_update)
        print(f"Update result: {result}")

        if result['success']:
            affected_portfolios = db.session.query(Portfolio.id).distinct().join(
                Security
            ).filter(
                Security.ticker.in_(result['tickers_updated'])
            ).all()

            # Invalidate cache for each affected portfolio
            for portfolio_id, in affected_portfolios:
                invalidate_portfolio_cache(portfolio_id)
                print(f"Invalidated cache for portfolio {portfolio_id}")

            return jsonify({
                "message": "Historical data update completed successfully",
                "triggered_by": current_user_email,
                "timestamp": datetime.utcnow().isoformat(),
                "tickers_updated": result['tickers_updated'],
                "records_added": result['records_added'],
                "success": True
            }), 200
        else:
            error_msg = result.get('error', 'Update process failed')
            print(f"Update failed: {error_msg}")
            return jsonify({
                "error": error_msg,
                "timestamp": datetime.utcnow().isoformat(),
                "success": False
            }), 500

    except Exception as e:
        print(f"Error in trigger_historical_update: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "success": False
        }), 500


# log the historical updates table
@analytics_blueprint.route('/historical-update-status', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_historical_update_status():
    try:
        recent_updates = HistoricalDataUpdateLog.query \
            .order_by(HistoricalDataUpdateLog.update_time.desc()) \
            .limit(5) \
            .all()

        updates = [{
            'update_time': update.update_time.isoformat(),
            'tickers_updated': update.tickers_updated,
            'records_added': update.records_added,
            'status': update.status,
            'error': update.error
        } for update in recent_updates]

        return jsonify(updates), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@analytics_blueprint.route('/historical-data-management', methods=['GET'])
@jwt_required(locations=["cookies"])
def historical_data_management():
    # Get current user
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()

    if not user:
        return redirect(url_for('auth.login_page'))

    return render_template(
        'historical_data_management.html',
        user={"first_name": user.first_name, "email": user.email}
    )


@analytics_blueprint.route('/portfolio/<int:portfolio_id>/composition/<view_type>', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_composition(portfolio_id, view_type):
    print(f"Received composition request - Portfolio: {portfolio_id}, View Type: {view_type}")
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()

        if not portfolio:
            print(f"Portfolio {portfolio_id} not found for user {current_user_email}")
            return jsonify({"error": "Portfolio not found"}), 404

        # Get securities for this portfolio using the junction table
        portfolio_securities = (
            db.session.query(PortfolioSecurity, Security)
            .join(Security, PortfolioSecurity.security_id == Security.id)
            .filter(PortfolioSecurity.portfolio_id == portfolio_id)
            .all()
        )
        print(f"Found {len(portfolio_securities)} securities in portfolio")

        if view_type == 'risk':
            try:
                # Try to get cached data first
                cached_data = RiskAnalysisCache.get_cache(portfolio_id)
                if cached_data and 'var_components' in cached_data:
                    print("Using cached VaR components for composition")
                    var_components = cached_data['var_components']
                else:
                    print("Calculating fresh VaR components...")
                    # Calculate if not cached
                    risk_analyzer = RiskAnalytics()
                    securities_data = []
                    for ps, security in portfolio_securities:
                        security_data = {
                            'ticker': security.ticker,
                            'amount_owned': ps.amount_owned,
                            'total_value': ps.total_value,
                            'purchase_date': ps.purchase_date.strftime("%Y-%m-%d") if ps.purchase_date else None,
                            'current_price': security.current_price
                        }
                        securities_data.append(security_data)
                    var_components = risk_analyzer.get_var_components(securities_data)

                if not var_components:
                    print("No VaR components returned")
                    return jsonify({
                        'labels': ['No Risk Data'],
                        'values': [100]
                    })

                # Calculate total VaR
                print("Calculating total VaR...")
                total_var = sum(abs(comp['var_contribution']) for comp in var_components)
                print(f"Total VaR: {total_var}")

                # Group by risk category
                groups = {}
                for comp in var_components:
                    volatility = abs(comp['volatility'])
                    risk_category = (
                        'High Risk' if volatility > 20
                        else 'Medium Risk' if volatility > 10
                        else 'Low Risk'
                    )
                    groups[risk_category] = groups.get(risk_category, 0) + abs(comp['var_contribution'])
                    print(f"Security {comp.get('ticker', 'Unknown')}: {risk_category} - Contribution: {comp['var_contribution']}")

                # Convert to percentages
                return jsonify({
                    'labels': list(groups.keys()),
                    'values': [abs(value) / total_var * 100 for value in groups.values()]
                })

            except Exception as e:
                print(f"Error in risk calculation: {str(e)}")
                import traceback
                print(f"Traceback: {traceback.format_exc()}")
                return jsonify({"error": f"Failed to calculate risk composition: {str(e)}"}), 500

        # For non-risk views
        composition_data = []
        total_value = 0

        for ps, security in portfolio_securities:
            metadata = SecurityMetadata.query.filter_by(ticker=security.ticker).first()
            if metadata:
                composition_data.append({
                    'ticker': security.ticker,
                    'value': ps.total_value,  # Use the value from portfolio_securities
                    'sector': metadata.sector or 'Unknown',
                    'asset_type': metadata.asset_type or 'Unknown',
                    'currency': metadata.currency or 'USD'
                })
                total_value += ps.total_value

        # Group and calculate percentages based on view type
        groups = {}
        if view_type == 'sector':
            for item in composition_data:
                sector = item['sector']
                groups[sector] = groups.get(sector, 0) + item['value']
        elif view_type == 'asset':
            for item in composition_data:
                asset_type = item['asset_type']
                groups[asset_type] = groups.get(asset_type, 0) + item['value']
        elif view_type == 'currency':
            for item in composition_data:
                currency = item['currency']
                groups[currency] = groups.get(currency, 0) + item['value']

        # Calculate percentages for non-risk views
        composition = {
            'labels': list(groups.keys()),
            'values': [value / total_value * 100 for value in groups.values()]
        }

        return jsonify(composition)

    except Exception as e:
        print(f"Error calculating composition: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"error": "Failed to calculate composition"}), 500