from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, render_template, redirect, url_for, make_response, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_jwt_extended import decode_token
from flask_jwt_extended import get_csrf_token
from backend import bcrypt, db
from backend.models import User, Portfolio, PortfolioSecurity
from backend.models import PortfolioFiles
import os
from werkzeug.utils import secure_filename

# Create a blueprint for authentication routes
auth_blueprint = Blueprint("auth", __name__)

# Define the upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Ensure the app's configuration is set up
@auth_blueprint.before_app_request
def configure_app():
    current_app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@auth_blueprint.route('/login', methods=['GET'])
def login_page():
    return render_template("login.html")


@auth_blueprint.route('/signup', methods=['GET'])
def signup_page():
    return render_template("signup.html")


# Handle JWT exceptions globally within this blueprint
@auth_blueprint.before_app_request
def check_jwt():
    if request.endpoint and "auth." in request.endpoint:
        if request.endpoint in ["auth.login_page", "auth.signup_page", "auth.signup", "auth.login", "auth.logout"]:
            print(f"Skipping JWT check for endpoint: {request.endpoint}")
            return
        try:
            # Debugging: Log the cookie
            jwt_cookie = request.cookies.get('access_token_cookie')
            print(f"JWT Cookie: {jwt_cookie}")

            # Debugging: Decode the token
            if jwt_cookie:
                from flask_jwt_extended import decode_token
                decoded_jwt = decode_token(jwt_cookie)
                print(f"Decoded JWT: {decoded_jwt}")

            # Verify the JWT
            verify_jwt_in_request(locations=["cookies"])
            print("JWT verification succeeded.")
        except NoAuthorizationError:
            print("NoAuthorizationError: Redirecting to login.")
            return redirect(url_for("auth.login_page"))
        except Exception as e:
            print(f"Unexpected JWT error: {e}")
            return redirect(url_for("auth.login_page"))


@auth_blueprint.route('/signup', methods=['POST'])
def signup():
    data = request.form

    # Check if the email already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({'message': 'Email already in use. Please use a different email.'}), 400

    # Hash the password
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    # Create a new user
    user = User(
        first_name=data['first_name'],
        last_name=data['last_name'],
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password
    )
    db.session.add(user)
    db.session.commit()

    return redirect(url_for('auth.login_page'))


@auth_blueprint.route('/login', methods=['POST'])
def login():
    data = request.form
    user = User.query.filter_by(email=data['email']).first()

    if user and bcrypt.check_password_hash(user.password_hash, data['password']):
        additional_claims = {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
        access_token = create_access_token(identity=user.email, additional_claims=additional_claims)

        # Provide CSRF token as a separate cookie
        csrf_token = get_csrf_token(access_token)

        response = make_response(redirect(url_for('auth.portfolio_overview')))
        response.set_cookie('access_token_cookie', access_token, httponly=True, samesite='Lax', secure=False)
        response.set_cookie('csrf_access_token', csrf_token)  # Add this line
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
        jwt_data = get_jwt()
        print("JWT Data:", jwt_data)
        return render_template('dashboard.html', body_class='dashboard-page', user=jwt_data)
    except Exception as e:
        print(f"Error in dashboard: {e}")
        return redirect(url_for('auth.login_page'))


@auth_blueprint.route('/portfolio-overview', methods=['GET'])
@jwt_required(locations=["cookies"])
def portfolio_overview():
    try:
        current_user_email = get_jwt_identity()
        if not current_user_email:
            print("No JWT identity found. Redirecting to login.")
            return redirect(url_for("auth.login_page"))

        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            print("User not found in database.")
            return redirect(url_for("auth.login_page"))

        portfolios = Portfolio.query.filter_by(user_id=user.id).all()
        uploaded_files = PortfolioFiles.query.filter_by(user_id=user.id).all()

        print(f"User {current_user_email} accessed portfolio overview.")  # Debugging
        return render_template(
            'portfolio_overview.html',
            body_class='portfolio-overview-page',
            user={"first_name": user.first_name, "email": user.email},
            portfolios=portfolios,
            uploaded_files=uploaded_files,
        )
    except Exception as e:
        print(f"Error in portfolio-overview: {e}")
        return redirect(url_for("auth.login_page"))


# @auth_blueprint.route('/portfolio-overview', methods=['GET'])
# @jwt_required(locations=["cookies"])
# def portfolio_overview():
#     try:
#         current_user_email = get_jwt_identity()
#         user = User.query.filter_by(email=current_user_email).first()
#
#         if not user:
#             return jsonify({"message": "User not found"}), 404
#
#         portfolios = Portfolio.query.filter_by(user_id=user.id).all()
#         portfolio_data = [
#             {
#                 "id": portfolio.id,
#                 "name": portfolio.name,
#                 "created_at": portfolio.created_at.strftime('%Y-%m-%d %H:%M:%S'),
#                 "total_holdings": portfolio.total_holdings,
#                 "last_value": portfolio.last_value,
#                 "day_change": portfolio.day_change,
#                 "one_year_gain": portfolio.one_year_gain,
#                 "one_year_return": portfolio.one_year_return,
#             }
#             for portfolio in portfolios
#         ]
#
#         return jsonify(portfolio_data), 200
#     except Exception as e:
#         print(f"Error in portfolio-overview: {e}")
#         return jsonify({"message": "An unexpected error occurred."}), 500


@auth_blueprint.route('/portfolio/<int:portfolio_id>', methods=['DELETE'])
@jwt_required(locations=["cookies"])
def delete_portfolio(portfolio_id):
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()

    if not user:
        return jsonify({"message": "User not found"}), 404

    portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
    if not portfolio:
        return jsonify({"message": "Portfolio not found"}), 404

    db.session.delete(portfolio)
    db.session.commit()
    return jsonify({"message": "Portfolio deleted successfully"}), 200


@auth_blueprint.route('/upload', methods=['POST'])
@jwt_required(locations=["cookies"])
def upload_file():
    try:
        current_user_email = get_jwt_identity()
        print(f"User attempting upload: {current_user_email}")  # Debugging

        if not current_user_email:
            print("No user authenticated.")
            return jsonify({"message": "Authentication required"}), 401

        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            print("User not found.")
            return jsonify({"message": "User not found"}), 404

        if 'file' not in request.files:
            print("No file part in request.")
            return jsonify({"message": "No file part"}), 400

        file = request.files['file']
        if file.filename == '':
            print("No file selected.")
            return jsonify({"message": "No selected file"}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        new_file = PortfolioFiles(
            user_id=user.id,
            filename=filename,
            uploaded_by=user.email,
        )
        db.session.add(new_file)
        db.session.commit()

        print(f"File {filename} uploaded successfully for user {user.email}.")
        return jsonify({"message": f"File {filename} uploaded successfully!"}), 200
    except Exception as e:
        print(f"Error in upload_file: {e}")
        return jsonify({"message": "An unexpected error occurred."}), 500


@auth_blueprint.route('/uploaded-files', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_uploaded_files():
    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()
    if not user:
        return jsonify({"message": "User not found"}), 404

    files = PortfolioFiles.query.filter_by(user_id=user.id).all()
    return jsonify([{
        "id": file.id,
        "filename": file.filename,
        "uploaded_at": file.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
        "updated_at": file.updated_at.strftime('%Y-%m-%d %H:%M:%S') if file.updated_at else None,
        "uploaded_by": user.email
    } for file in files])


@auth_blueprint.route('/stock-data', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_stock_data():
    ticker = request.args.get("ticker")
    if not ticker:
        return jsonify({"message": "Ticker is required"}), 400

    # Mocked response - replace with a real API call
    stock_data = {
        "ticker": ticker.upper(),
        "name": f"Mocked Name for {ticker.upper()}",
        "industry": "Mocked Industry",
        "valueChangeDay": "+1.25%",
        "totalGainLoss1Y": "+20.50%",
    }
    return jsonify(stock_data)


@auth_blueprint.route('/create-portfolio', methods=['POST'])
@jwt_required(locations=["cookies"])
def create_portfolio():
    try:
        data = request.json
        # ensure user's identity
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        print(f"Creating portfolio for user: {current_user_email}")
        print(f"Portfolio details: {data}")

        if not user:
            return jsonify({"message": "User not found"}), 404

        # Create Portfolio
        portfolio = Portfolio(
            user_id=user.id,
            name=data["name"],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_holdings=len(data["stocks"]),  # this is number of stocks owned, not a dollar value
        )
        db.session.add(portfolio)
        db.session.flush()  # flush to get the portfolio ID

        # Add Securities
        for stock in data["stocks"]:
            portfolio_security = PortfolioSecurity(
                portfolio_id=portfolio.id,
                ticker=stock["ticker"],
                name=stock["name"],
                industry=stock["industry"],
                shares=stock["amount"],  # Amount entered in the manual creation

            )
            db.session.add(portfolio_security)

        db.session.commit()

        return jsonify({
            "message": "Portfolio created successfully!",
            "portfolio": {
                "id": portfolio.id,
                "name": portfolio.name,
                "created_at": portfolio.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                "total_holdings": portfolio.total_holdings
            }
        }), 200
    except Exception as e:
        print(f"Error creating portfolio: {e}")
        return jsonify({"message": "An error occurred while creating the portfolio."}), 500

