from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from .. import db

analytics_blueprint = Blueprint('analytics', __name__)


@analytics_blueprint.route('/portfolio/<int:portfolio_id>/risk', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_risk(portfolio_id):
    try:
        from ..models import Portfolio, Security  # Import here instead

        current_user_email = get_jwt_identity()
        user = Security.query.filter_by(email=current_user_email).first()
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()

        if not portfolio:
            return jsonify({"error": "Portfolio not found"}), 404

        # Rest of your function...

    except Exception as e:
        print(f"Error fetching risk metrics: {str(e)}")
        return jsonify({"error": "Failed to fetch risk metrics"}), 500