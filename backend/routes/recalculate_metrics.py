"""
Routes for recalculating portfolio metrics.
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from backend.models import User
from backend.services.price_update_service import PriceUpdateService

# Create blueprint
recalculate_blueprint = Blueprint('recalculate', __name__)


@recalculate_blueprint.route('/api/recalculate-all-metrics', methods=['POST'])
@jwt_required(locations=["cookies"])
def recalculate_all_metrics():
    """
    Recalculate metrics for all portfolios.
    This is useful when metrics like total return are not showing correctly.
    """
    try:
        # Get current user
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        
        if not user:
            return jsonify({"message": "User not found"}), 404
        
        # Create price update service
        price_service = PriceUpdateService()
        
        # Recalculate metrics for all portfolios
        result = price_service.recalculate_all_portfolio_metrics()
        
        if result.get('success', False):
            return jsonify({
                "message": "Portfolio metrics recalculated successfully",
                "success_count": result.get('success_count', 0),
                "error_count": result.get('error_count', 0),
                "total": result.get('total', 0)
            }), 200
        else:
            return jsonify({
                "message": "Failed to recalculate portfolio metrics",
                "error": result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        import traceback
        print(f"Error in recalculate_all_metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500


@recalculate_blueprint.route('/api/portfolio/<int:portfolio_id>/recalculate', methods=['POST'])
@jwt_required(locations=["cookies"])
def recalculate_portfolio_metrics(portfolio_id):
    """
    Recalculate metrics for a specific portfolio.
    This is useful when metrics like total return are not showing correctly.
    """
    try:
        # Get current user
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        
        if not user:
            return jsonify({"message": "User not found"}), 404
        
        # Create price update service
        price_service = PriceUpdateService()
        
        # Recalculate metrics for the specified portfolio
        result = price_service.update_portfolio_metrics(portfolio_id)
        
        if result.get('success', False):
            return jsonify({
                "message": "Portfolio metrics recalculated successfully",
                "portfolio_id": portfolio_id,
                "total_value": result.get('total_value', 0),
                "day_change": result.get('day_change', 0),
                "total_gain": result.get('total_gain', 0),
                "total_return": result.get('total_return', 0)
            }), 200
        else:
            return jsonify({
                "message": "Failed to recalculate portfolio metrics",
                "error": result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        import traceback
        print(f"Error in recalculate_portfolio_metrics: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"message": f"An error occurred: {str(e)}"}), 500