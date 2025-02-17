import asyncio
from datetime import datetime

from flask import Blueprint, jsonify, render_template, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func

from backend.models import User, Portfolio, Security, HistoricalDataUpdateLog, SecurityHistoricalData, SecurityMetadata
from backend.analytics.risk_calculations import RiskAnalytics, calculate_credit_risk
from backend import db
from backend.routes.auth_routes import get_risk_composition
from backend.services.historical_data_service import HistoricalDataService

analytics_blueprint = Blueprint('analytics', __name__)


@analytics_blueprint.route('/portfolio/<int:portfolio_id>/risk', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_risk(portfolio_id):

    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()

        if not portfolio:
            return jsonify({"error": "Portfolio not found"}), 404

        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()
        risk_analyzer = RiskAnalytics()

        securities_data = [{
            'ticker': s.ticker,
            'amount_owned': s.amount_owned,
            'purchase_date': s.purchase_date.strftime("%Y-%m-%d") if s.purchase_date else None,
            'current_price': s.current_price,
            'total_value': s.total_value
        } for s in securities]

        # Calculate metrics
        var_data = risk_analyzer.calculate_dynamic_var(securities_data)
        credit_risk = calculate_credit_risk(securities_data)
        # putting the beta calculation on hold for right now.
        # beta = risk_analyzer.calculate_portfolio_beta(securities_data, portfolio.total_value)

        var_components = risk_analyzer.get_var_components(securities_data)

        latest_update = db.session.query(
            func.max(SecurityHistoricalData.updated_at)
        ).scalar()

        return jsonify({
            'portfolio_name': portfolio.name,
            'total_value': portfolio.total_value,
            'var_metrics': var_data,
            'credit_risk': credit_risk,
            'beta': 0.0,  # beta,
            'var_components': var_components,
            'securities': securities_data,
            'latest_update': latest_update.strftime('%Y-%m-%d %H:%M:%S') if latest_update else None

        })

    except Exception as e:
        print(f"Error calculating risk metrics: {str(e)}")
        return jsonify({"error": "Failed to calculate risk metrics"}), 500


@analytics_blueprint.route('/trigger-historical-update', methods=['POST'])
@jwt_required(locations=["cookies"])
def trigger_historical_update():
    log_entry = None
    try:
        current_user_email = get_jwt_identity()
        print(f"Historical update triggered by user: {current_user_email}")

        # Create log entry
        log_entry = HistoricalDataUpdateLog(
            status='started',
            tickers_updated=0,
            records_added=0
        )
        db.session.add(log_entry)
        db.session.commit()
        print(f"Created log entry with ID: {log_entry.id}")

        service = HistoricalDataService()
        result = service.update_historical_data()

        if result['success']:
            log_entry.status = 'completed'
            log_entry.tickers_updated = result['tickers_updated']
            log_entry.records_added = result['records_added']
            db.session.commit()

            return jsonify({
                "message": "Historical data update completed successfully",
                "triggered_by": current_user_email,
                "timestamp": datetime.utcnow().isoformat(),
                "tickers_updated": result['tickers_updated'],
                "records_added": result['records_added']
            }), 200
        else:
            log_entry.status = 'failed'
            log_entry.error = result.get('error', 'Update process failed')
            db.session.commit()
            return jsonify({
                "error": result.get('error', 'Update process failed'),
                "timestamp": datetime.utcnow().isoformat()
            }), 500

    except Exception as e:
        print(f"Error in trigger_historical_update: {str(e)}")
        if log_entry:
            log_entry.status = 'failed'
            log_entry.error = str(e)
            db.session.commit()
        return jsonify({
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
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
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        # Join with metadata table to get the composition data, since i built historical table first...
        query = db.session.query(
            Security,
            SecurityMetadata
        ).join(
            SecurityMetadata,
            Security.ticker == SecurityMetadata.ticker
        ).filter(
            Security.portfolio_id == portfolio_id
        )

        securities = query.all()
        total_value = sum(s[0].total_value for s in securities)

        if view_type == 'sector':
            groups = {}
            for security, metadata in securities:
                sector = metadata.sector or 'Unknown'
                groups[sector] = groups.get(sector, 0) + security.total_value
        elif view_type == 'asset_type':
            # Similar grouping for asset type
            pass
        elif view_type == 'currency':
            # Similar grouping for currency
            pass
        elif view_type == 'risk':
            # Use existing risk components data
            return get_risk_composition(portfolio_id)

        # Calculate percentages
        composition = {
            'labels': list(groups.keys()),
            'values': [value / total_value * 100 for value in groups.values()]
        }

        return jsonify(composition)

    except Exception as e:
        print(f"Error calculating composition: {str(e)}")
        return jsonify({"error": "Failed to calculate composition"}), 500