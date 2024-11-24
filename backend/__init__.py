from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager

from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))


# Initialize Flask app
app = Flask(__name__)

# Configurations
import os

# Define the absolute path to the database file
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'users.db')}"


app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback_secret_key')  # Fallback key for development
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'fallback_jwt_key')  # Fallback key for development

# Initialize extensions
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
