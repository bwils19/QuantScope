from datetime import datetime, timezone, time

import requests
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, make_response, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_jwt_extended import decode_token
from flask_jwt_extended import get_csrf_token
from backend import bcrypt, db
from backend.models import User, Portfolio, Security, StockCache
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
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return redirect(url_for("auth.login_page"))

        # Get user's portfolios
        portfolios = Portfolio.query.filter_by(user_id=user.id).all()

        # Update prices if we have portfolios
        if portfolios:
            try:
                # Get unique tickers from user's portfolios
                unique_tickers = (
                    db.session.query(Security.ticker)
                    .join(Portfolio)
                    .filter(Portfolio.user_id == user.id)
                    .distinct()
                    .all()
                )

                tickers = [t[0] for t in unique_tickers]
                api_key = os.getenv('ALPHA_VANTAGE_KEY')

                for ticker in tickers:
                    # Check if cache is stale (older than today)
                    cache = StockCache.query.filter_by(ticker=ticker).first()
                    if not cache or cache.date < datetime.utcnow().date():
                        try:
                            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
                            response = requests.get(url)
                            data = response.json()

                            if 'Global Quote' in data:
                                quote = data['Global Quote']
                                current_price = float(quote['05. price'])
                                prev_close = float(quote['08. previous close'])

                                # Update or create cache
                                if not cache:
                                    cache = StockCache(ticker=ticker)

                                cache.date = datetime.utcnow().date()
                                cache.data = {
                                    'currentPrice': current_price,
                                    'previousClose': prev_close,
                                    'changePercent': float(quote['10. change percent'].rstrip('%'))
                                }
                                db.session.add(cache)

                                # Update securities with this ticker
                                securities = Security.query.filter_by(ticker=ticker).all()
                                for security in securities:
                                    old_value = security.total_value
                                    security.current_price = current_price
                                    security.total_value = security.amount_owned * current_price
                                    security.value_change = security.amount_owned * (current_price - prev_close)
                                    security.value_change_pct = (security.value_change / (
                                                old_value - security.value_change)) * 100 if old_value != security.value_change else 0
                                    security.unrealized_gain = security.total_value - (
                                                security.amount_owned * security.purchase_price)
                                    security.unrealized_gain_pct = ((security.total_value / (
                                                security.amount_owned * security.purchase_price)) - 1) * 100

                            # Respect API rate limits
                            time.sleep(12)  # Alpha Vantage free tier limit is 5 calls per minute - will buy premium

                        except Exception as e:
                            print(f"Error updating {ticker}: {str(e)}")
                            continue

                # Update portfolio totals
                for portfolio in portfolios:
                    portfolio.total_value = sum(s.total_value for s in portfolio.securities)
                    portfolio.day_change = sum(s.value_change for s in portfolio.securities)
                    portfolio.day_change_pct = (portfolio.day_change / (
                                portfolio.total_value - portfolio.day_change)) * 100 if portfolio.total_value != portfolio.day_change else 0

                    total_cost = sum(s.amount_owned * s.purchase_price for s in portfolio.securities)
                    portfolio.unrealized_gain = portfolio.total_value - total_cost
                    portfolio.unrealized_gain_pct = ((
                                                                 portfolio.total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

                db.session.commit()

            except Exception as e:
                print(f"Error updating prices: {str(e)}")
                db.session.rollback()

        uploaded_files = PortfolioFiles.query.filter_by(user_id=user.id).all()

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


@auth_blueprint.route('/portfolio/<int:portfolio_id>', methods=['DELETE'])
@jwt_required(locations=["cookies"])
def delete_portfolio(portfolio_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        # Delete related securities first (if cascade isn't set up)
        Security.query.filter_by(portfolio_id=portfolio_id).delete()

        # Delete the portfolio
        db.session.delete(portfolio)
        db.session.commit()

        return jsonify({"message": "Portfolio deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting portfolio: {e}")
        db.session.rollback()
        return jsonify({"message": "Failed to delete portfolio"}), 500


@auth_blueprint.route('/upload', methods=['POST'])
@jwt_required(locations=["cookies"])
def upload_file():
    print("Upload endpoint hit")
    try:
        # Verify JWT token first
        try:
            verify_jwt_in_request(locations=["cookies"])
        except Exception as e:
            print(f"JWT verification failed: {e}")
            return jsonify({"message": "Authentication required"}), 401

        current_user_email = get_jwt_identity()
        print(f"Upload attempt by user: {current_user_email}")

        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            print("User not found in database")
            return jsonify({"message": "User not found"}), 404

        if 'file' not in request.files:
            print("No file in request")
            return jsonify({"message": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            print("Empty filename")
            return jsonify({"message": "No file selected"}), 400

        filename = secure_filename(file.filename)
        upload_folder = current_app.config['UPLOAD_FOLDER']

        # Ensure upload folder exists
        if not os.path.exists(upload_folder):
            print(f"Creating upload folder: {upload_folder}")
            os.makedirs(upload_folder)

        filepath = os.path.join(upload_folder, filename)
        print(f"Saving file to: {filepath}")
        file.save(filepath)

        new_file = PortfolioFiles(
            user_id=user.id,
            filename=filename,
            uploaded_by=user.email,
        )
        print(f"Creating database record for file")
        db.session.add(new_file)
        db.session.commit()
        print(f"File record created successfully")

        return jsonify({
            "message": f"File {filename} uploaded successfully!",
            "file_id": new_file.id
        }), 200

    except Exception as e:
        print(f"Error in upload_file: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({"message": str(e)}), 500


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
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        data = request.json
        stocks = data.get("stocks", [])

        portfolio = Portfolio(
            name=data["name"],
            user_id=user.id,
            total_holdings=len(stocks)
        )

        db.session.add(portfolio)
        db.session.flush()  # Get portfolio ID

        total_value = 0
        total_cost = 0  # This will be our basis for unrealized gain/loss

        for stock in stocks:
            ticker = stock["ticker"]
            cache = StockCache.query.filter_by(ticker=ticker).first()

            if not cache:
                stock_data = {
                    'currentPrice': stock['totalValue'] / stock['amount'],
                    'previousClose': (stock['totalValue'] - stock['valueChange']) / stock['amount'],
                    'changePercent': (stock['valueChange'] / (stock['totalValue'] - stock['valueChange'])) * 100
                }

                cache = StockCache(
                    ticker=ticker,
                    date=datetime.utcnow().date(),
                    data=stock_data
                )
                db.session.add(cache)

            price_data = cache.data
            current_price = float(price_data['currentPrice'])
            amount = float(stock["amount"])

            # Calculate cost basis and current value
            cost_basis = amount * current_price  # Initial purchase cost
            current_value = amount * current_price

            security = Security(
                portfolio_id=portfolio.id,
                ticker=ticker,
                name=stock["name"],
                exchange=stock.get("exchange", ""),
                amount_owned=amount,
                purchase_price=current_price,
                current_price=current_price,
                total_value=current_value,
                value_change=float(stock['valueChange']),
                value_change_pct=float(price_data['changePercent']),
                unrealized_gain=current_value - cost_basis,  # Add this
                unrealized_gain_pct=((current_value / cost_basis) - 1) * 100  # Add this
            )

            total_value += current_value
            total_cost += cost_basis

            db.session.add(security)

        # Update portfolio metrics
        portfolio.total_value = total_value
        portfolio.day_change = sum(float(s['valueChange']) for s in stocks)
        portfolio.day_change_pct = (portfolio.day_change / (total_value - portfolio.day_change)) * 100
        portfolio.unrealized_gain = total_value - total_cost
        portfolio.unrealized_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

        db.session.commit()

        return jsonify({
            "message": "Portfolio created successfully!",
            "portfolio": {
                "id": portfolio.id,
                "name": portfolio.name,
                "total_holdings": portfolio.total_holdings,
                "total_value": portfolio.total_value
            }
        })

    except Exception as e:
        print(f"Error: {e}")
        db.session.rollback()
        return jsonify({"message": str(e)}), 500


@auth_blueprint.route('/portfolio/<int:portfolio_id>/securities', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_securities(portfolio_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()
        securities_data = [{
            'ticker': s.ticker,
            'name': s.name,
            'amount_owned': s.amount_owned,
            'current_price': s.current_price,
            'total_value': s.total_value,
            'value_change': s.value_change,
            'value_change_pct': s.value_change_pct,
            'unrealized_gain': s.unrealized_gain,
            'unrealized_gain_pct': s.unrealized_gain_pct
        } for s in securities]

        return jsonify({
            'portfolio_id': portfolio_id,
            'securities': securities_data
        }), 200

    except Exception as e:
        print(f"Error fetching portfolio securities: {e}")
        return jsonify({"message": "An error occurred while fetching portfolio securities"}), 500


@auth_blueprint.route('/stock-cache/<symbol>', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_cached_stock(symbol):
    cache = StockCache.query.filter_by(ticker=symbol) \
        .order_by(StockCache.date.desc()) \
        .first()

    if cache:
        return jsonify({
            'data': cache.data,
            'date': cache.date.isoformat()
        })
    return jsonify({'data': None}), 404


@auth_blueprint.route('/stock-cache', methods=['POST'])
@jwt_required(locations=["cookies"])
def cache_stock_data():
    data = request.json
    symbol = data['symbol']

    # Update or create cache entry
    cache = StockCache.query.filter_by(ticker=symbol).first()
    if not cache:
        cache = StockCache(
            ticker=symbol,
            date=datetime.utcnow().date(),
            data=data['data']
        )
    else:
        cache.date = datetime.utcnow().date()
        cache.data = data['data']

    db.session.add(cache)
    db.session.commit()

    return jsonify({'message': 'Cache updated'}), 200