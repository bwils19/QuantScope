from flask import Flask, render_template
from backend import db, bcrypt, jwt
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from datetime import timedelta
import os


def create_app():
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

    # Add a root route
    @app.route("/")
    def home():
        return render_template("home.html")

    return app


if __name__ == "__main__":
    app = create_app()

    # Create tables if not already created
    with app.app_context():
        db.create_all()

    app.run(debug=True)
