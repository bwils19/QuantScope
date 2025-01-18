from datetime import datetime, timezone, time

import requests
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, make_response, current_app, send_file
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
from backend.utils.file_handlers import parse_portfolio_file, format_preview_data

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
    """Verify JWT token for protected routes"""
    # Skip JWT check for these endpoints
    public_endpoints = [
        "auth.login_page",
        "auth.signup_page",
        "auth.signup",
        "auth.login",
        "auth.logout"
    ]

    if request.endpoint and "auth." in request.endpoint:
        if request.endpoint in public_endpoints:
            return

        try:
            verify_jwt_in_request(locations=["cookies"])
        except NoAuthorizationError:
            return redirect(url_for("auth.login_page"))
        except Exception as e:
            print(f"JWT verification error: {e}")
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
    """Handle login form submission"""
    try:
        data = request.form
        user = User.query.filter_by(email=data['email']).first()

        if user and bcrypt.check_password_hash(user.password_hash, data['password']):
            additional_claims = {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
            access_token = create_access_token(identity=user.email, additional_claims=additional_claims)
            csrf_token = get_csrf_token(access_token)

            # Create response with redirect
            response = make_response(redirect(url_for('auth.portfolio_overview')))

            # Set secure cookie flags
            response.set_cookie(
                'access_token_cookie',
                access_token,
                httponly=True,
                secure=True,  # Require HTTPS
                samesite='Lax',
                max_age=7200  # 2 hours
            )
            response.set_cookie(
                'csrf_access_token',
                csrf_token,
                secure=True,
                samesite='Lax',
                max_age=7200
            )
            return response

        # Invalid credentials
        if not user:
            return jsonify({
                    "status": "error",
                    "message": "No account found with that email address"
                }), 401
        else:
            return jsonify({
                    "status": "error",
                    "message": "Invalid password"
                }), 401

    except Exception as e:
        print(f"Error in login: {e}")
        return jsonify({
            "status": "error",
            "message": "An error occurred during login"
        }), 500


@auth_blueprint.route('/logout', methods=['GET'])
def logout():
    response = make_response(redirect(url_for('auth.login_page')))
    response.delete_cookie('access_token_cookie')
    response.delete_cookie('csrf_access_token')
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
        # Get the current user's identity
        current_user_email = get_jwt_identity()
        if not current_user_email:
            return redirect(url_for('auth.login_page'))

        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return redirect(url_for('auth.login_page'))

        portfolios = Portfolio.query.filter_by(user_id=user.id).order_by(Portfolio.created_at.desc()).all()

        # Calculate dashboard statistics
        total_portfolio_value = sum(p.total_value for p in portfolios) if portfolios else 0
        total_day_change = sum(p.day_change for p in portfolios) if portfolios else 0
        total_day_change_pct = (total_day_change / (
                    total_portfolio_value - total_day_change) * 100) if total_portfolio_value != total_day_change else 0

        # Calculate total unrealized gain/loss
        total_unrealized_gain = sum(p.unrealized_gain for p in portfolios) if portfolios else 0
        total_unrealized_gain_pct = sum(p.unrealized_gain_pct for p in portfolios) / len(
            portfolios) if portfolios else 0

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
            # uploaded_files=uploaded_files,
            dashboard_stats={
                'total_value': total_portfolio_value,
                'day_change': total_day_change,
                'day_change_pct': total_day_change_pct,
                'total_gain': total_unrealized_gain,
                'total_gain_pct': total_unrealized_gain_pct
            }
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


@auth_blueprint.route('/download-portfolio-template')
def download_portfolio_template():
    """Provide template file for portfolio uploads"""
    try:
        template_path = os.path.join(current_app.root_path, 'static', 'templates', 'portfolio_template.csv')
        return send_file(
            template_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name='portfolio_template.csv'
        )
    except Exception as e:
        print(f"Error providing template: {e}")
        return jsonify({"message": "Error downloading template"}), 500


@auth_blueprint.route('/preview-portfolio-file', methods=['POST'])
@jwt_required(locations=["cookies"])
def preview_portfolio_file():
    """Preview and validate uploaded portfolio file"""
    try:
        if 'file' not in request.files:
            return jsonify({"message": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"message": "No file selected"}), 400

        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

        # Save file temporarily
        file.save(filepath)

        try:
            # Parse and validate file
            df, validation_summary = parse_portfolio_file(filepath)
            preview_data = format_preview_data(df)

            # Create a record in PortfolioFiles
            portfolio_file = PortfolioFiles(
                user_id=user.id,
                filename=filename,
                uploaded_by=user.email
            )
            db.session.add(portfolio_file)
            db.session.commit()

            return jsonify({
                'preview_data': preview_data,
                'summary': validation_summary,
                'message': 'File processed successfully',
                'file_id': portfolio_file.id  # Add file ID to response
            })

        finally:
            pass

    except Exception as e:
        print(f"Error in preview: {str(e)}")
        return jsonify({
            'message': f"Error processing file: {str(e)}"
        }), 400


@auth_blueprint.route('/create-portfolio-from-file/<int:file_id>', methods=['POST'])
@jwt_required(locations=["cookies"])
def create_portfolio_from_file(file_id):
    """Create a portfolio from an uploaded file"""
    print("\n=== Starting Portfolio Creation ===")
    print(f"File ID: {file_id}")

    try:
        # Log request details
        print("\n=== Request Details ===")
        print(f"Method: {request.method}")
        print(f"Headers: {dict(request.headers)}")
        print(f"Content-Type: {request.headers.get('Content-Type')}")
        print(f"Raw Data: {request.get_data()}")

        # Parse JSON data
        print("\n=== Parsing JSON ===")
        try:
            raw_data = request.get_data()
            print(f"Raw request data: {raw_data}")
            data = request.get_json(force=True)
            print(f"Parsed JSON data: {data}")
        except Exception as e:
            print(f"JSON parsing error: {str(e)}")
            return jsonify({"message": f"Invalid JSON data: {str(e)}"}), 400

        # Get portfolio name
        print("\n=== Processing Portfolio Name ===")
        portfolio_name = data.get('portfolio_name', '').strip()
        print(f"Portfolio Name: {portfolio_name}")

        if not portfolio_name:
            print("Error: Portfolio name is required")
            return jsonify({"message": "Portfolio name is required"}), 400

        # Get user
        print("\n=== Getting User ===")
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        print(f"User Email: {current_user_email}")

        if not user:
            print("Error: User not found")
            return jsonify({"message": "User not found"}), 404

        # Get file record
        print("\n=== Getting File Record ===")
        file_record = PortfolioFiles.query.get(file_id)
        if not file_record or file_record.user_id != user.id:
            print(f"Error: File not found or unauthorized for ID {file_id}")
            return jsonify({"message": "File not found"}), 404

        # Process file
        print("\n=== Processing File ===")
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_record.filename)
        print(f"File Path: {file_path}")

        if not os.path.exists(file_path):
            print(f"Error: File not found at path: {file_path}")
            return jsonify({"message": "File not found on server"}), 404

        # Create portfolio
        print("\n=== Creating Portfolio ===")
        df, _ = parse_portfolio_file(file_path)
        print(f"Parsed file columns: {df.columns.tolist()}")

        portfolio = Portfolio(
            name=portfolio_name,
            user_id=user.id,
            total_holdings=len(df)
        )
        db.session.add(portfolio)
        db.session.flush()
        print(f"Created portfolio with ID: {portfolio.id}")

        # Add securities
        print("\n=== Adding Securities ===")
        total_value = 0
        total_cost = 0

        for _, row in df.iterrows():
            if row['validation_status'] == 'valid':
                security = Security(
                    portfolio_id=portfolio.id,
                    ticker=row['ticker'],
                    name=row.get('name', row['ticker']),
                    amount_owned=float(row['amount']),
                    purchase_price=float(row.get('purchase_price', 0)) if 'purchase_price' in row else 0,
                    current_price=float(row.get('current_price', 0)) if 'current_price' in row else 0
                )

                security.total_value = security.amount_owned * (security.current_price or security.purchase_price)
                total_value += security.total_value
                total_cost += security.amount_owned * security.purchase_price

                db.session.add(security)
                print(f"Added security: {security.ticker}")

        # Update totals
        print("\n=== Updating Portfolio Totals ===")
        portfolio.total_value = total_value
        portfolio.unrealized_gain = total_value - total_cost
        portfolio.unrealized_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

        db.session.commit()
        print("Portfolio creation completed successfully")

        # Clean up
        print("\n=== Cleanup ===")
        try:
            os.remove(file_path)
            print(f"Removed temporary file: {file_path}")
        except Exception as e:
            print(f"Warning: Failed to remove temporary file: {e}")

        return jsonify({
            "message": "Portfolio created successfully",
            "portfolio_id": portfolio.id
        }), 200

    except Exception as e:
        print("\n=== Error Details ===")
        print(f"Error type: {type(e)}")
        print(f"Error message: {str(e)}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        if 'db' in locals():
            db.session.rollback()
        return jsonify({"message": f"Error creating portfolio: {str(e)}"}), 500


@auth_blueprint.route('/portfolio/<int:portfolio_id>/update', methods=['POST'])
@jwt_required(locations=["cookies"])
def update_portfolio(portfolio_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        data = request.get_json()
        changes = data.get('changes', [])

        print("Received changes:", data)

        for change in changes:
            print("Processing change:", change)
            security_id = change.get('security_id')

            if change.get('new'):  # Handle new securities
                print("Adding new security:", change)
                security = Security(
                    portfolio_id=portfolio_id,
                    ticker=change['ticker'],
                    name=change['name'],
                    amount_owned=float(change['amount']),
                    current_price=float(change['current_price']),
                    total_value=float(change['total_value']),
                    value_change=float(change['value_change']),
                    value_change_pct=float(change['value_change_pct']),
                    unrealized_gain=float(change.get('unrealized_gain', 0)),
                    unrealized_gain_pct=float(change.get('unrealized_gain_pct', 0))
                )
                db.session.add(security)
                print("New security added to session")

            else:  # Handle existing securities
                security = Security.query.filter_by(id=security_id, portfolio_id=portfolio_id).first()
                if security:
                    if change.get('deleted'):
                        db.session.delete(security)
                    elif 'amount' in change:
                        # Your existing update logic for amount changes
                        pass

        # Update portfolio totals
        db.session.flush()  # Ensure all security changes are reflected
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Calculate totals with None checks
        portfolio.total_value = sum((s.total_value or 0) for s in securities)
        portfolio.day_change = sum((s.value_change or 0) for s in securities)
        portfolio.total_holdings = len(securities)

        # Update other portfolio metrics...

        db.session.commit()
        print("Updated portfolio values:", {
            "total_value": portfolio.total_value,
            "total_holdings": portfolio.total_holdings,
            "day_change": portfolio.day_change
        })

        return jsonify({
            "message": "Portfolio updated successfully",
            "portfolio_id": portfolio_id,
            "total_value": portfolio.total_value,
            "total_holdings": portfolio.total_holdings,
            "day_change": portfolio.day_change,
            "day_change_pct": portfolio.day_change_pct,
            "unrealized_gain": portfolio.unrealized_gain,
            "unrealized_gain_pct": portfolio.unrealized_gain_pct
        }), 200

    except Exception as e:
        print(f"Error in update_portfolio: {str(e)}")
        db.session.rollback()
        return jsonify({"message": f"Failed to update portfolio: {str(e)}"}), 500

