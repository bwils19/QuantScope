from flask import Blueprint, request, jsonify
from backend import db, bcrypt
from backend.models import User  # Import the User model
from flask_jwt_extended import create_access_token
from flask import render_template

# Create a blueprint for authentication routes
auth_blueprint = Blueprint("auth", __name__)


@auth_blueprint.route('/login', methods=['GET'])
def login_page():
    return render_template("login.html")


@auth_blueprint.route('/signup', methods=['GET'])
def signup_page():
    return render_template("signup.html")


@auth_blueprint.route('/signup', methods=['POST'])
def signup():
    data = request.json
    # Hash the user's password
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user = User(name=data['name'], email=data['email'], password_hash=hashed_password)
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User created successfully!'})


@auth_blueprint.route('/login', methods=['POST'])
def login():
    data = request.json
    # Query the database for the user
    user = User.query.filter_by(email=data['email']).first()
    if user and bcrypt.check_password_hash(user.password_hash, data['password']):
        # Create a JWT token
        access_token = create_access_token(identity={'name': user.name, 'email': user.email})
        return jsonify({'access_token': access_token})
    return jsonify({'message': 'Invalid credentials!'}), 401