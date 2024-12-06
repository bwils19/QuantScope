from flask import Flask, redirect, url_for
from flask_jwt_extended import get_jwt_identity

from backend import db, bcrypt, jwt
from datetime import timedelta
import os
from dotenv import load_dotenv


def create_app():
    # Load environment variables
    load_dotenv()

    # Initialize Flask app
    app = Flask(__name__)

    # Set app configurations
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=2)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'supersecretkey')

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    # Register blueprints
    from backend.routes.auth_routes import auth_blueprint
    from backend.routes.stock_routes import stock_blueprint
    app.register_blueprint(auth_blueprint, url_prefix="/auth")
    app.register_blueprint(stock_blueprint)

    # Root route
    @app.route("/")
    def home():
        # Redirect based on authentication status
        jwt_identity = get_jwt_identity()
        return (
            redirect(url_for("auth.portfolio_overview"))
            if jwt_identity
            else redirect(url_for("auth.login_page"))
        )

    return app


if __name__ == "__main__":
    app = create_app()

    # Create database tables if not already created
    with app.app_context():
        db.create_all()

    # Run the app
    app.run(debug=True)
