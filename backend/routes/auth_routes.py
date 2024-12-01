from flask import Blueprint, request, jsonify
from flask import render_template
from flask import session, redirect, url_for, make_response
from flask_jwt_extended import create_access_token, jwt_required, get_jwt
from backend import app, db, bcrypt
from backend.models import User
import os
from werkzeug.utils import secure_filename

# Create a blueprint for authentication routes
auth_blueprint = Blueprint("auth", __name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@auth_blueprint.route('/login', methods=['GET'])
def login_page():
    return render_template("login.html")


@auth_blueprint.route('/signup', methods=['GET'])
def signup_page():
    return render_template("signup.html")


@auth_blueprint.route('/signup', methods=['POST'])
def signup():
    data = request.form  # Or request.json if using JSON payload
    print(f"received data: {data}")

    # Check if the email already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        # Flash a message or return an error response
        return jsonify({'message': 'Email already in use. Please use a different email.'}), 400

    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    # Create and save user
    user = User(
        first_name=data['first_name'],
        last_name=data['last_name'],
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password)
    db.session.add(user)
    db.session.commit()

    # return jsonify({'message': 'User created successfully!'})
    return redirect(url_for('auth.login_page'))


@auth_blueprint.route('/login', methods=['POST'])
def login():
    data = request.form
    user = User.query.filter_by(email=data['email']).first()

    if user and bcrypt.check_password_hash(user.password_hash, data['password']):
        # Create a JWT token
        additional_claims = {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
        access_token = create_access_token(identity=user.email, additional_claims=additional_claims)

        # Set the token in a secure cookie
        response = make_response(redirect(url_for('auth.dashboard')))
        response.set_cookie(
            'access_token_cookie',
            access_token,
            httponly=True,  # prevents JavaScript access to the cookie
            secure=True,  # Use only over HTTPS (set to False for local dev)
            samesite='Strict'  # prevent cross-site request forgery
        )
        return response

    return jsonify({"message": "Invalid credentials"}), 401


@auth_blueprint.route('/logout', methods=['GET'])
def logout():
    response = make_response(redirect(url_for('auth.login_page')))
    response.delete_cookie('access_token_cookie')
    return response


@auth_blueprint.route('/dashboard', methods=['GET'])
@jwt_required(locations=["cookies"])
def dashboard():
    try:
        # Extract JWT data
        jwt_data = get_jwt()
        first_name = jwt_data.get("first_name", "User")
        email = jwt_data.get("email")

        # Debug: Print JWT data to confirm claims
        print("JWT Data:", jwt_data)

        # Render the dashboard
        return render_template('dashboard.html', user={"first_name": first_name, "email": email})
    except Exception as e:
        print(f"Error in dashboard: {e}")
        return jsonify({"msg": "Unauthorized"}), 401


# @app.route('/user/<email>', methods=['GET'])
# @jwt_required()
# def user_dashboard(email):
#     # Verify user access
#     current_user = get_jwt_identity()
#     if current_user != email:
#         return jsonify({"message": "Unauthorized"}), 403
#
#     # Retrieve user-specific data
#     # Example: Past uploads (fetch from DB or storage) - will delete this when testing upload functionality
#     user_files = [
#         {"filename": "file1.csv", "uploaded_at": "2024-11-01"},
#         {"filename": "file2.xlsx", "uploaded_at": "2024-11-02"}
#     ]
#     return jsonify({
#         "email": current_user,
#         "files": user_files
#     })

@app.route('/upload', methods=['POST'])
@jwt_required()
def upload_file():
    if 'file' not in request.files:
        return jsonify({"message": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"message": "No selected file"}), 400
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    # Store file metadata in the database (optional)
    return jsonify({"message": f"File {filename} uploaded successfully!"}), 200
