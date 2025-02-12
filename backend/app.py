from flask import Flask, redirect, url_for, jsonify, make_response
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_migrate import Migrate
from backend import db, bcrypt, jwt
from datetime import timedelta
import os
from dotenv import load_dotenv
from backend.tasks import init_scheduler
from backend.commands import load_historical_data

from backend.models import User, Portfolio, Security


def create_app(test_config=None):
    # Load environment variables
    load_dotenv()

    # Initialize Flask app
    app = Flask(__name__)

    if test_config is None:
        # Set app configurations
        upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        app.config['UPLOAD_FOLDER'] = upload_folder

        basedir = os.path.abspath(os.path.dirname(__file__))
        app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'users.db')}"
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=2)
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'supersecretkey')
    else:
        # Load test config if passed in
        app.config.update(test_config)

    lock_file = 'sessions_cleared.lock'
    if os.path.exists(lock_file):
        os.remove(lock_file)

    # Initialize extensions
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)

    with app.app_context():

        from backend.models import User, Portfolio, Security

        @app.before_request
        def clear_sessions_on_startup():
            lock_file = 'sessions_cleared.lock'

            if not os.path.exists(lock_file):
                # Delete cookies on the first request after restart
                response = make_response(redirect(url_for('auth.login_page')))
                response.delete_cookie('access_token_cookie')
                response.delete_cookie('csrf_access_token')

                # Create the lock file to mark that sessions have been cleared
                with open(lock_file, 'w') as f:
                    f.write('cleared')

                return response

        # Create database tables
        db.create_all()

        # Initialize migrations
        migrate = Migrate(app, db)

        # Register blueprints
        from backend.routes.auth_routes import auth_blueprint
        from backend.routes.stock_routes import stock_blueprint
        from .routes.analytics_routes import analytics_blueprint
        app.register_blueprint(auth_blueprint, url_prefix="/auth")
        app.register_blueprint(stock_blueprint)
        app.register_blueprint(analytics_blueprint, url_prefix='/analytics')

        app.cli.add_command(load_historical_data)

    # Root route
    @app.route("/")
    def home():
        try:
            # only allow access with valid JWT
            verify_jwt_in_request(locations=["cookies"])
            jwt_identity = get_jwt_identity()
            if jwt_identity:
                return redirect(url_for('auth.portfolio_overview'))
        except Exception as e:
            print(f"Error in home route: {e}")
            return redirect(url_for('auth.login_page'))

        return redirect(url_for('auth.login_page'))

    @app.route('/api/key')
    def get_api_key():
        try:
            api_key = os.getenv('ALPHA_VANTAGE_KEY')
            if not api_key:
                return jsonify({'error': 'API key not found'}), 500
            return jsonify({'apiKey': api_key})
        except Exception as e:
            print(f"Error fetching API key: {e}")
            return jsonify({'error': 'Internal server error'}), 500

    # Initialize scheduler if not in debug mode
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        scheduler = init_scheduler(app)
        app.scheduler = scheduler

    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    app.run(debug=True)