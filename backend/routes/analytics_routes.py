from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.models import User, Portfolio, Security  # Use absolute imports
from backend.analytics.risk_calculations import RiskAnalytics, calculate_credit_risk
from backend import db

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
        # beta = risk_analyzer.calculate_portfolio_beta(securities_data, portfolio.total_value)

        var_components = risk_analyzer.get_var_components(securities_data)

        return jsonify({
            'portfolio_name': portfolio.name,
            'total_value': portfolio.total_value,
            'var_metrics': var_data,
            'credit_risk': credit_risk,
            'beta': 0.0,  # beta,
            'var_components': var_components,
            'securities': securities_data
        })

    except Exception as e:
        print(f"Error calculating risk metrics: {str(e)}")
        return jsonify({"error": "Failed to calculate risk metrics"}), 500