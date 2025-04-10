from flask import Flask, redirect, url_for, jsonify, make_response
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_migrate import Migrate
from backend import db, bcrypt, jwt
from datetime import timedelta, datetime
import os
from dotenv import load_dotenv
from backend.tasks import init_scheduler
from backend.commands import load_historical_data
from backend.services.email_service import mail
from backend.utils.data_utils import fetch_and_process_stress_scenarios
from backend.logging_config import setup_logging
from flask_mail import Mail, Message
from backend.celery_app import configure_celery, celery

from backend.models import User, Portfolio, Security, StressScenario

# Initialize Mail outside the app factory
mail = Mail()


def create_app(test_config=None):
    # Load environment variables
    load_dotenv()

    app = Flask(__name__)
    loggers = setup_logging(app)

    if test_config is None:
        upload_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        app.config['UPLOAD_FOLDER'] = upload_folder

        basedir = os.path.abspath(os.path.dirname(__file__))

        database_url = os.getenv('DATABASE_URL')
        if database_url:
            # If using PostgreSQL, ensure URL has correct format for SQLAlchemy
            if database_url.startswith('postgres://'):
                database_url = database_url.replace('postgres://', 'postgresql://')
            app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        else:
            basedir = os.path.abspath(os.path.dirname(__file__))
            app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'users.db')}"

        #app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'instance', 'users.db')}"
        app.config['LOGGERS'] = loggers
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=2)
        app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'supersecretkey')

        app.config['MAIL_SERVER'] = 'smtp.gmail.com'
        app.config['MAIL_PORT'] = 587
        app.config['MAIL_USE_TLS'] = True
        app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
        app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')
        mail.init_app(app)
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
        from backend.celery_app import configure_celery
        configure_celery(app)  # configure the celery app to run tasks
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

        # Create database tables and log confirmation
        # print(f"Creating database tables with URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
        db.create_all()

        # Initialize migrations
        migrate = Migrate(app, db)

        # Register blueprints
        from backend.routes.auth_routes import auth_blueprint
        from backend.routes.stock_routes import stock_blueprint
        from backend.routes.analytics_routes import \
            analytics_blueprint  # Fixed typo from 'analytics_routes' to 'analytics_blueprint'
        from backend.routes.recalculate_metrics import recalculate_blueprint
        
        app.register_blueprint(auth_blueprint, url_prefix="/auth")
        app.register_blueprint(stock_blueprint)
        app.register_blueprint(analytics_blueprint, url_prefix='/analytics')
        app.register_blueprint(recalculate_blueprint, url_prefix='/api')

        app.cli.add_command(load_historical_data)
        from backend.utils.diagnostic import check_date_issues
        check_date_issues()
    # configure_celery(app)

    # Root route
    @app.route("/")
    def home():
        try:
            # Only allow access with valid JWT
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
            
    @app.route('/api/health')
    def health_check():
        """Health check endpoint to verify system status"""
        try:
            # Check database connection
            db_status = "ok"
            try:
                db.session.execute("SELECT 1")
            except Exception as e:
                db_status = f"error: {str(e)}"
                
            # Check Celery/Redis connection
            celery_status = "ok"
            try:
                from backend.services.price_update_service import scheduled_price_update
                # Send a simple ping task
                ping = scheduled_price_update.apply_async(args=[], countdown=0)
                ping.revoke()  # Revoke it immediately so it doesn't actually run
            except Exception as e:
                celery_status = f"error: {str(e)}"
                
            # Check environment variables
            env_vars = {
                "ALPHA_VANTAGE_KEY": "present" if os.getenv('ALPHA_VANTAGE_KEY') else "missing",
                "DATABASE_URL": "present" if os.getenv('DATABASE_URL') else "missing",
                "REDIS_URL": "present" if os.getenv('REDIS_URL') else "missing"
            }
            
            return jsonify({
                'status': 'ok',
                'timestamp': datetime.now().isoformat(),
                'components': {
                    'database': db_status,
                    'celery': celery_status,
                    'environment': env_vars
                }
            })
        except Exception as e:
            app.logger.error(f"Health check failed: {str(e)}")
            return jsonify({
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500

    
    app.logger.info("Using Celery for task scheduling. APScheduler disabled.")

    # Run stress scenarios data population with detailed logging
    # with app.app_context():
    #     print("Starting to fetch and process stress scenarios...")
    #     try:
    #         fetch_and_process_stress_scenarios(app)  # Pass the app instance here
    #         print("Completed fetching and processing stress scenarios. Checking stress_scenarios table...")
    #         # Verify data in stress_scenarios table
    #         scenarios = StressScenario.query.all()
    #         print(f"Number of stress scenarios in DB: {len(scenarios)}")
    #         for scenario in scenarios:
    #             print(
    #                 f"Scenario: {scenario.event_name}, Index: {scenario.index_name}, Price Change: {scenario.price_change_pct}%")
    
    # Clear the RiskAnalysisCache table on startup
    with app.app_context():
        try:
            from backend.models import RiskAnalysisCache
            RiskAnalysisCache.query.delete()
            db.session.commit()
            print("Cleared RiskAnalysisCache table on startup")
        except Exception as e:
            print(f"Error clearing RiskAnalysisCache table: {str(e)}")
    #     except Exception as e:
    #         print(f"Error processing stress scenarios: {e}")
    @app.cli.command('load_stress_scenarios')
    def load_stress_scenarios():
        """Load stress scenario data into the database."""
        with app.app_context():
            print("Starting to fetch and process stress scenarios...")
            try:
                fetch_and_process_stress_scenarios(app)
                print("Completed fetching and processing stress scenarios. Checking stress_scenarios table...")
                scenarios = StressScenario.query.all()
                print(f"Number of stress scenarios in DB: {len(scenarios)}")
                for scenario in scenarios:
                    print(
                        f"Scenario: {scenario.event_name}, Index: {scenario.index_name}, Price Change: {scenario.price_change_pct}%")
            except Exception as e:
                print(f"Error processing stress scenarios: {e}")

    return app


def send_update_notification(status, details):
    try:
        msg = Message(
            f"Historical Data Update {status}",
            sender=app.config['MAIL_USERNAME'],
            recipients=[os.getenv('ADMIN_EMAIL')]  # Your notification email
        )

        msg.body = f"""
        Historical Data Update {status}

        Time: {datetime.now()}
        Details: {details}

        Tickers Updated: {details.get('tickers_updated', 0)}
        Records Added: {details.get('records_added', 0)}
        Status: {details.get('status', 'Unknown')}
        Error (if any): {details.get('error', 'None')}
        """

        mail.send(msg)
        print(f"Notification email sent: {status}")
    except Exception as e:
        print(f"Failed to send email notification: {e}")

# Add code to clear the RiskAnalysisCache table in the create_app function


if __name__ == "__main__":
    try:
        app = create_app()
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
