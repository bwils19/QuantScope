from flask import Flask, redirect, url_for, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_migrate import Migrate
from backend import db, bcrypt, jwt
from datetime import timedelta
import os
from dotenv import load_dotenv
from backend.tasks import init_scheduler

from backend.models import User, Portfolio, Security


def create_app():
    try:
        # Load environment variables
        load_dotenv()

        # Initialize Flask app
        app = Flask(__name__)

        upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        app.config['UPLOAD_FOLDER'] = upload_folder
        print(f"Upload folder configured: {upload_folder}")

        # Set app configurations
        basedir = os.path.abspath(os.path.dirname(__file__))
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'users.db')}"
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=2)
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'supersecretkey')

        # Initialize extensions
        db.init_app(app)
        bcrypt.init_app(app)
        jwt.init_app(app)

        migrate = Migrate(app, db)

        # Register blueprints
        from backend.routes.auth_routes import auth_blueprint
        from backend.routes.stock_routes import stock_blueprint
        app.register_blueprint(auth_blueprint, url_prefix="/auth")
        app.register_blueprint(stock_blueprint)

        # Root route
        @app.route("/")
        def home():
            try:
                # Check if the user has a valid JWT token
                verify_jwt_in_request(optional=True)  # Optional check allows for unauthenticated access
                jwt_identity = get_jwt_identity()
                if jwt_identity:
                    # Redirect to the portfolio overview page if logged in
                    return redirect(url_for('auth.portfolio_overview'))
                else:
                    # Redirect to the login page if not logged in
                    return redirect(url_for('auth.login_page'))
            except Exception as e:
                print(f"Error in home route: {e}")  # Debugging
                # In case of any issues (e.g., invalid or missing token), route to login
                return redirect(url_for('auth.login_page'))

            # Route to send API key securely
        @app.route('/api/key')
        def get_api_key():
            try:
                api_key = os.getenv('ALPHA_VANTAGE_KEY')  # Fetch the API key from the environment variable
                if not api_key:
                    return jsonify({'error': 'API key not found'}), 500
                return jsonify({'apiKey': api_key})  # Send the API key securely to the frontend
            except Exception as e:
                print(f"Error fetching API key: {e}")
                return jsonify({'error': 'Internal server error'}), 500

        if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            scheduler = init_scheduler(app)

        return app

    except Exception as e:
        print(f"Error in create_app: {e}")  # Debugging
        return None


if __name__ == "__main__":
    app = create_app()

    if app is None:
        print("Failed to create the Flask app. Exiting.")
    else:
        # Create database tables if not already created
        with app.app_context():
            db.create_all()

        # Run the app
        app.run(debug=True)
