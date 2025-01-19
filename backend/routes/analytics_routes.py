from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models import Portfolio, Security
from ..analytics.risk_calculations import RiskAnalytics

analytics_blueprint = Blueprint('analytics', __name__)
risk_analytics = RiskAnalytics()


@analytics_blueprint.route('/portfolio/<int:portfolio_id>/risk', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_risk(portfolio_id):
    try:
        portfolio = Portfolio.query.get_or_404(portfolio_id)
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Convert securities to dict format expected by RiskAnalytics
        securities_data = [{
            'ticker': s.ticker,
            'amount_owned': s.amount_owned,
            'current_price': s.current_price,
            'total_value': s.total_value
        } for s in securities]

        # Calculate all risk metrics
        var_95 = risk_analytics.calculate_var(securities_data)
        credit_risk = risk_analytics.calculate_credit_risk(securities_data)
        beta = risk_analytics.calculate_portfolio_beta(securities_data, portfolio.total_value)

        return jsonify({
            'var_95': var_95,
            'credit_risk': credit_risk,
            'beta': beta
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500