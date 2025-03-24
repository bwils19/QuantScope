import logging
from datetime import datetime, timedelta
import time

import requests
import sqlalchemy
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, make_response, current_app, send_file
from flask_jwt_extended import create_access_token, jwt_required, get_jwt, get_jwt_identity, verify_jwt_in_request, \
    set_access_cookies
from flask_jwt_extended.exceptions import NoAuthorizationError
from flask_jwt_extended import decode_token
from flask_jwt_extended import get_csrf_token
from sqlalchemy import func

from backend import bcrypt, db
from backend.models import User, Portfolio, Security, StockCache, SecurityHistoricalData, Watchlist, PortfolioSecurity
from backend.models import PortfolioFiles

from backend.analytics.risk_calculations import RiskAnalytics

from contextlib import contextmanager
from sqlalchemy.orm import Session

import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from backend.services.price_update_service import PriceUpdateService
from backend.tasks import is_market_open
from backend.utils.file_handlers import parse_portfolio_file, format_preview_data
from backend.services.cache_service import invalidate_user_cache
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import requests

auth_blueprint = Blueprint("auth", __name__)

# Define the upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def get_session_with_retries():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[408, 429, 500, 502, 503, 504],
    )
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session


def fetch_stock_data(ticker, api_key):
    try:
        session = get_session_with_retries()
        url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data for {ticker}: {str(e)}")
        return None


def fetch_prices_for_portfolio(tickers):
    """Fetch prices for all tickers in a portfolio efficiently"""
    logger = logging.getLogger('api')
    logger.info(f"Fetching prices for {len(tickers)} tickers")

    load_dotenv()
    api_key = os.getenv('ALPHA_VANTAGE_KEY')
    results = {}
    failed_tickers = []

    # Get cached prices first
    cached_prices = StockCache.query.filter(StockCache.ticker.in_(tickers)).all()
    cache_dict = {cache.ticker: cache for cache in cached_prices}

    # Identify which tickers need API calls
    to_fetch = [ticker for ticker in tickers if ticker not in cache_dict
                or (datetime.utcnow().date() - cache_dict[ticker].date).days > 0]

    logger.info(f"Found {len(cache_dict)} cached prices, need to fetch {len(to_fetch)}")

    # Create a session with retries
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    # Fetch from API with minimal rate limiting
    for i, ticker in enumerate(to_fetch):
        try:
            # Small pause between requests
            if i > 0 and i % 20 == 0:
                time.sleep(1)  # Short pause every 20 requests

            logger.info(f"Fetching price for {ticker} ({i + 1}/{len(to_fetch)})")
            url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"
            response = session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.debug(f"Raw API response for {ticker}: {data}")

            if data and 'Global Quote' in data and data['Global Quote'].get('05. price'):
                quote = data['Global Quote']
                price_data = {
                    'currentPrice': float(quote['05. price']),
                    'previousClose': float(quote['08. previous close']),
                    'changePercent': float(quote['10. change percent'].rstrip('%'))
                }

                # Create or update cache entry
                if ticker in cache_dict:
                    cache = cache_dict[ticker]
                    cache.date = datetime.utcnow().date()
                    cache.data = price_data
                    logger.info(f"Updated cache for {ticker}: ${price_data['currentPrice']}")
                else:
                    cache = StockCache(
                        ticker=ticker,
                        date=datetime.utcnow().date(),
                        data=price_data
                    )
                    db.session.add(cache)
                    logger.info(f"Created new cache for {ticker}: ${price_data['currentPrice']}")

                results[ticker] = price_data
            else:
                logger.warning(f"No price data returned for {ticker} - API response: {data}")
                failed_tickers.append(ticker)

        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {str(e)}")
            failed_tickers.append(ticker)

        # Commit every 50 securities
        if i > 0 and i % 50 == 0:
            try:
                db.session.commit()
                logger.info(f"Committed batch of 50 price updates")
            except Exception as commit_error:
                logger.error(f"Error committing price batch: {commit_error}")
                db.session.rollback()

    # Final commit for remaining price updates
    try:
        db.session.commit()
        logger.info(f"Committed final batch of price updates")
    except Exception as commit_error:
        logger.error(f"Error committing final price batch: {commit_error}")
        db.session.rollback()

    # Add all cached results to the results dictionary
    for ticker, cache in cache_dict.items():
        if ticker not in results and ticker not in failed_tickers:
            results[ticker] = cache.data
            logger.info(f"Using cached data for {ticker}: ${cache.data['currentPrice']}")

    if failed_tickers:
        logger.warning(f"Failed to fetch prices for {len(failed_tickers)} tickers: {', '.join(failed_tickers[:10])}" +
                       (f"... and {len(failed_tickers) - 10} more" if len(failed_tickers) > 10 else ""))

    return results


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


@auth_blueprint.before_app_request
def check_jwt():
    """Verify JWT token for protected routes"""
    # Skip JWT check for these endpoints
    public_endpoints = [
        "auth.login_page",
        "auth.signup_page",
        "auth.signup",
        "auth.login",
        "auth.logout",
        "auth.refresh"
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

    # these two checks need to generate a user-facing error message.

    # Check if the email already exists
    existing_user = User.query.filter_by(email=data['email']).first()
    if existing_user:
        return jsonify({'message': 'Email already in use. Please use a different email.'}), 400

    # check if a username is already taken
    existing_user = User.query.filter_by(username=data['username']).first()
    if existing_user:
        return jsonify({'message': 'Username already in use. Please select a different username.'}), 400

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
                # secure=True,  # Require HTTPS
                secure=False,
                samesite='Lax',
                max_age=7200  # will log out after 2 hours
            )
            response.set_cookie(
                'csrf_access_token',
                csrf_token,
                # secure=True,
                secure=False,
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


@auth_blueprint.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    try:
        # Create new access token
        access_token = create_access_token(identity=get_jwt_identity())

        response = jsonify({'msg': 'Token refreshed successfully'})

        # Set the JWT cookies in the response
        set_access_cookies(response, access_token)

        return response, 200

    except Exception as e:
        return jsonify({'msg': 'Token refresh failed', 'error': str(e)}), 401


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


# I think the session_scope is causing problems in the updating. need to come back and revisit this.
@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = db.create_scoped_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        print(f"Session error: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def should_update_price(cache_entry):
    """Determine if price update is needed"""
    if not cache_entry:
        return True

    cache_date = cache_entry.date
    now = datetime.utcnow().date()

    # Don't update if market is closed
    if not is_market_open():
        return False

    # Don't update if cache is from today and less than 5 minutes old
    if cache_date == now:
        cache_time = cache_entry.updated_at
        five_mins_ago = datetime.utcnow() - timedelta(minutes=5)
        return cache_time < five_mins_ago

    return True


@auth_blueprint.route('/portfolio-overview', methods=['GET'])
@jwt_required(locations=["cookies"])
def portfolio_overview():
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return redirect(url_for('auth.login_page'))

        portfolios = Portfolio.query.filter_by(user_id=user.id).order_by(Portfolio.created_at.desc()).all()

        # Get all unique tickers for this user's portfolios
        unique_tickers = (
            db.session.query(Security.ticker)
            .join(PortfolioSecurity, Security.id == PortfolioSecurity.security_id)
            .join(Portfolio, Portfolio.id == PortfolioSecurity.portfolio_id)
            .filter(Portfolio.user_id == user.id)
            .distinct()
            .all()
        )
        tickers = [t[0] for t in unique_tickers]

        # Determine the most recent market date
        today = datetime.now().date()
        is_weekend = today.weekday() >= 5
        days_since_friday = today.weekday() - 4 if is_weekend else 0
        most_recent_market_date = today - timedelta(days=days_since_friday)

        # Get the most recent historical data for each ticker
        latest_prices = {}
        for ticker in tickers:
            latest_data = db.session.query(
                SecurityHistoricalData
            ).filter(
                SecurityHistoricalData.ticker == ticker,
                SecurityHistoricalData.date <= most_recent_market_date
            ).order_by(
                SecurityHistoricalData.date.desc()
            ).first()

            if latest_data:
                # Get previous day data for accurate day change calculation
                prev_day = db.session.query(
                    SecurityHistoricalData
                ).filter(
                    SecurityHistoricalData.ticker == ticker,
                    SecurityHistoricalData.date < latest_data.date
                ).order_by(
                    SecurityHistoricalData.date.desc()
                ).first()

                latest_prices[ticker] = {
                    'current_price': latest_data.close_price,
                    'previous_close': prev_day.close_price if prev_day else latest_data.close_price,
                    'date': latest_data.date,
                    'has_historical': True
                }

        # Update portfolio securities with the most recent data
        for portfolio in portfolios:
            portfolio_total_value = 0
            portfolio_day_change = 0
            total_cost = 0

            # Use the portfolio_securities relationship instead of securities
            portfolio_securities = (
                db.session.query(PortfolioSecurity, Security)
                .join(Security, PortfolioSecurity.security_id == Security.id)
                .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                .all()
            )

            for ps, security in portfolio_securities:
                latest_data = latest_prices.get(security.ticker)

                if latest_data:
                    # Update with historical data
                    security.current_price = latest_data['current_price']
                    ps.total_value = ps.amount_owned * latest_data['current_price']

                    # Calculate day change using historical data
                    ps.value_change = ps.amount_owned * (
                            latest_data['current_price'] - latest_data['previous_close']
                    )

                    base_value = ps.amount_owned * latest_data['previous_close']
                    ps.value_change_pct = (ps.value_change / base_value) * 100 if base_value != 0 else 0

                # Calculate total gain/loss if purchase price is available
                position_cost = ps.amount_owned * ps.purchase_price if ps.purchase_price else 0
                ps.total_gain = ps.total_value - position_cost
                if position_cost and position_cost != 0:
                    ps.total_gain_pct = ((ps.total_value / position_cost) - 1) * 100
                else:
                    ps.total_gain_pct = 0

                # Accumulate portfolio totals
                portfolio_total_value += ps.total_value
                portfolio_day_change += ps.value_change
                total_cost += position_cost

            # Update portfolio metrics
            portfolio.total_value = portfolio_total_value
            portfolio.day_change = portfolio_day_change

            if total_cost > 0:
                portfolio.total_gain = portfolio_total_value - total_cost
                portfolio.total_gain_pct = ((portfolio_total_value / total_cost) - 1) * 100
            else:
                portfolio.total_gain = 0
                portfolio.total_gain_pct = 0

            if portfolio_total_value != portfolio_day_change:
                base_value = portfolio_total_value - portfolio_day_change
                portfolio.day_change_pct = (portfolio_day_change / base_value) * 100 if base_value != 0 else 0
            else:
                portfolio.day_change_pct = 0

        # Calculate dashboard statistics
        total_portfolio_value = sum(p.total_value or 0 for p in portfolios) if portfolios else 0
        total_day_change = sum(p.day_change or 0 for p in portfolios) if portfolios else 0
        total_total_gain = sum(p.total_gain or 0 for p in portfolios) if portfolios else 0
        total_total_gain_pct = (
                sum(p.total_gain_pct or 0 for p in portfolios) / len(portfolios)) if portfolios else 0

        if total_portfolio_value != total_day_change:
            base_value = total_portfolio_value - total_day_change
            total_day_change_pct = (total_day_change / base_value) * 100 if base_value != 0 else 0
        else:
            total_day_change_pct = 0

        # Get most recent historical data update timestamp
        latest_update = db.session.query(
            func.max(SecurityHistoricalData.updated_at)
        ).scalar()

        # Get watchlist data
        watchlist_data = []
        if user:
            watchlist_items = Watchlist.query.filter_by(user_id=user.id).all()
            for item in watchlist_items:
                # Get latest price data
                latest_price_data = (
                    db.session.query(SecurityHistoricalData)
                    .filter(
                        SecurityHistoricalData.ticker == item.ticker,
                        SecurityHistoricalData.date <= most_recent_market_date
                    )
                    .order_by(SecurityHistoricalData.date.desc())
                    .first()
                )

                previous_day_data = (
                    db.session.query(SecurityHistoricalData)
                    .filter(
                        SecurityHistoricalData.ticker == item.ticker,
                        SecurityHistoricalData.date < latest_price_data.date if latest_price_data else most_recent_market_date
                    )
                    .order_by(SecurityHistoricalData.date.desc())
                    .first()
                )

                current_price = latest_price_data.close_price if latest_price_data else None
                previous_close = previous_day_data.close_price if previous_day_data else (
                    current_price if current_price else None
                )

                day_change = (current_price - previous_close) if current_price and previous_close else None
                day_change_pct = ((
                                              current_price - previous_close) / previous_close * 100) if current_price and previous_close and previous_close != 0 else None

                watchlist_data.append({
                    'id': item.id,
                    'ticker': item.ticker,
                    'name': item.name,
                    'exchange': item.exchange,
                    'current_price': current_price,
                    'day_change': day_change,
                    'day_change_pct': day_change_pct,
                    'latest_update': latest_price_data.date if latest_price_data else None
                })

        print("\n\n===== DEBUGGING PORTFOLIO DATA =====")
        print(f"Number of portfolios: {len(portfolios)}")
        for i, portfolio in enumerate(portfolios):
            print(f"Portfolio {i + 1}: {portfolio.name}, ID: {portfolio.id}")
            print(f"  Total value: {portfolio.total_value}")
            print(f"  Day change: {portfolio.day_change}")

            # Debug portfolio securities
            portfolio_securities = (
                db.session.query(PortfolioSecurity, Security)
                .join(Security, PortfolioSecurity.security_id == Security.id)
                .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                .all()
            )
            print(f"  Number of securities: {len(portfolio_securities)}")
            for j, (ps, security) in enumerate(portfolio_securities):
                print(
                    f"    Security {j + 1}: {security.ticker}, Amount: {ps.amount_owned}, Current price: {security.current_price}")
                print(f"      Total value: {ps.total_value}, Day change: {ps.value_change}")

        portfolio_view_data = []
        for portfolio in portfolios:
            # Get portfolio securities with their associated security data
            portfolio_securities = (
                db.session.query(PortfolioSecurity, Security)
                .join(Security, PortfolioSecurity.security_id == Security.id)
                .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                .all()
            )

            # Create portfolio object
            portfolio_obj = {
                'id': portfolio.id,
                'name': portfolio.name,
                'user_id': portfolio.user_id,
                'created_at': portfolio.created_at,
                'updated_at': portfolio.updated_at,
                'total_holdings': portfolio.total_holdings,
                'total_value': portfolio.total_value,
                'day_change': portfolio.day_change,
                'day_change_pct': portfolio.day_change_pct,
                'total_gain': portfolio.total_gain,
                'total_gain_pct': portfolio.total_gain_pct,
                'total_return': portfolio.total_return,
                'total_return_pct': portfolio.total_return_pct,
                'securities': []
            }

            # Add securities to the portfolio object
            for ps, security in portfolio_securities:
                security_obj = {
                    'id': ps.id,
                    'ticker': security.ticker,
                    'name': security.name,
                    'exchange': security.exchange,
                    'amount_owned': ps.amount_owned,
                    'purchase_date': ps.purchase_date.strftime('%Y-%m-%d') if ps.purchase_date else None,
                    'purchase_price': ps.purchase_price,
                    'current_price': security.current_price,
                    'total_value': ps.total_value,
                    'value_change': ps.value_change,
                    'value_change_pct': ps.value_change_pct,
                    'total_gain': ps.total_gain,
                    'total_gain_pct': ps.total_gain_pct
                }
                portfolio_obj['securities'].append(security_obj)

            portfolio_view_data.append(portfolio_obj)

        print("\n===== DEBUGGING PORTFOLIO VIEW DATA =====")
        print(f"Number of portfolio views: {len(portfolio_view_data)}")
        for i, p_view in enumerate(portfolio_view_data):
            print(f"Portfolio view {i + 1}: {p_view['name']}, ID: {p_view['id']}")
            print(f"  Total value: {p_view['total_value']}")
            print(f"  Day change: {p_view['day_change']}")
            print(f"  Number of securities: {len(p_view['securities'])}")
            for j, s in enumerate(p_view['securities']):
                print(
                    f"    Security {j + 1}: {s['ticker']}, Amount: {s['amount_owned']}, Current price: {s['current_price']}")
                print(f"      Total value: {s['total_value']}, Day change: {s['value_change']}")

        # Then modify the return statement to use portfolio_view_data
        return render_template(
            'portfolio_overview.html',
            body_class='portfolio-overview-page',
            user={"first_name": user.first_name, "email": user.email},
            portfolios=portfolio_view_data,
            dashboard_stats={
                'total_value': total_portfolio_value,
                'day_change': total_day_change,
                'day_change_pct': total_day_change_pct,
                'total_gain': total_total_gain,
                'total_gain_pct': total_total_gain_pct
            },
            latest_update=latest_update,
            watchlist=watchlist_data
        )

    except Exception as e:
        print(f"Error in portfolio-overview: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return redirect(url_for("auth.login_page"))


@auth_blueprint.route('/security-historical/<symbol>', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_security_historical(symbol):
    try:
        # Get latest 90 days of data matching your schema
        historical_data = (
            db.session.query(SecurityHistoricalData)
            .filter_by(ticker=symbol)
            .order_by(SecurityHistoricalData.date.desc())
            .limit(90)
            .all()
        )

        if not historical_data:
            return jsonify({"message": "No historical data found"}), 404

        # Format data using your actual column names
        data = {
            'dates': [record.date.strftime('%Y-%m-%d') for record in reversed(historical_data)],
            'prices': [float(record.close_price) for record in reversed(historical_data)],
            'open_prices': [float(record.open_price) for record in reversed(historical_data)],
            'high_prices': [float(record.high_price) for record in reversed(historical_data)],
            'low_prices': [float(record.low_price) for record in reversed(historical_data)],
            'adjusted_closes': [float(record.adjusted_close) for record in reversed(historical_data)],
            'volumes': [int(record.volume) for record in reversed(historical_data)]
        }

        # Get the latest price and previous day's price for calculations
        latest = historical_data[0]
        previous = historical_data[1] if len(historical_data) > 1 else None

        if latest and previous:
            data['current_price'] = float(latest.close_price)
            data['previous_close'] = float(previous.close_price)
            data['day_change'] = data['current_price'] - data['previous_close']
            data['day_change_pct'] = (data['day_change'] / data['previous_close']) * 100
        else:
            data['current_price'] = float(latest.close_price) if latest else None
            data['previous_close'] = None
            data['day_change'] = None
            data['day_change_pct'] = None

        return jsonify(data), 200

    except Exception as e:
        print(f"Error fetching historical data: {e}")
        return jsonify({"message": "Failed to fetch historical data"}), 500


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

    # mock data for now until implementation
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
        db.session.flush()

        total_value = 0
        total_cost = 0

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
                purchase_date=datetime.strptime(stock["purchase_date"], '%Y-%m-%d') if stock.get("purchase_date") else None,
                purchase_price=current_price,
                current_price=current_price,
                total_value=current_value,
                value_change=float(stock['valueChange']),
                value_change_pct=float(price_data['changePercent']),
                total_gain=current_value - cost_basis,  # Add this
                total_gain_pct=((current_value / cost_basis) - 1) * 100
            )

            total_value += current_value
            total_cost += cost_basis

            db.session.add(security)

        # Update portfolio metrics
        portfolio.total_value = total_value
        portfolio.day_change = sum(float(s['valueChange']) for s in stocks)
        portfolio.day_change_pct = (portfolio.day_change / (total_value - portfolio.day_change)) * 100
        portfolio.total_gain = total_value - total_cost
        portfolio.total_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

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

        # Query portfolio securities with joined security data
        result = db.session.query(
            PortfolioSecurity,
            Security
        ).join(
            Security, PortfolioSecurity.security_id == Security.id
        ).filter(
            PortfolioSecurity.portfolio_id == portfolio_id
        ).all()

        securities_data = []

        for ps, security in result:
            securities_data.append({
                'id': ps.id,  # Use junction table ID
                'ticker': security.ticker,
                'name': security.name,
                'amount_owned': ps.amount_owned,
                'current_price': security.current_price,
                'total_value': ps.total_value,
                'value_change': ps.value_change,
                'value_change_pct': ps.value_change_pct,
                'purchase_date': ps.purchase_date.strftime('%Y-%m-%d') if ps.purchase_date else None,
                'total_gain': ps.total_gain,
                'total_gain_pct': ps.total_gain_pct,
                'latest_close': security.current_price, # Using current price as latest close
                'latest_close_date': datetime.now().strftime('%Y-%m-%d')
            })

        # Get the latest update timestamp
        latest_update = None
        try:
            latest_update = db.session.query(func.max(SecurityHistoricalData.updated_at)).scalar()
            if not latest_update:
                latest_update = datetime.now()
        except Exception as e:
            print(f"Error getting latest update timestamp: {e}")
            latest_update = datetime.now()

        return jsonify({
            'portfolio_id': portfolio_id,
            'portfolio_name': portfolio.name,
            'securities': securities_data,
            'latest_update': latest_update.strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    except Exception as e:
        import traceback
        print(f"Error fetching portfolio securities: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"message": "An error occurred while fetching portfolio securities", "error": str(e)}), 500


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
    try:
        with session_scope() as session:
            data = request.json
            symbol = data['symbol']

            cache = session.query(StockCache).filter_by(ticker=symbol).with_for_update().first()
            if not cache:
                cache = StockCache(
                    ticker=symbol,
                    date=datetime.utcnow().date(),
                    data=data['data']
                )
                session.add(cache)
            else:
                cache.date = datetime.utcnow().date()
                cache.data = data['data']

            return jsonify({'message': 'Cache updated'}), 200
    except Exception as e:
        print(f"Error updating cache: {e}")
        return jsonify({'error': str(e)}), 500


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
    try:
        current_token = get_jwt()
        token_expiry = datetime.fromtimestamp(current_token["exp"])

        # If token is close to expiring (within 5 minutes), refresh it
        if token_expiry - datetime.now() < timedelta(minutes=5):
            # Create new access token with same identity and claims
            access_token = create_access_token(
                identity=get_jwt_identity(),
                additional_claims={k: v for k, v in current_token.items() if k not in ['exp', 'iat', 'jti', 'type']}
            )
            resp = make_response(jsonify({"message": "Token refreshed"}))
            set_access_cookies(resp, access_token)

        try:
            data = request.get_json(force=True)
            portfolio_name = data.get('portfolio_name', '').strip()
            preview_data = data.get('preview_data', [])

            if not portfolio_name:
                return jsonify({"message": "Portfolio name is required"}), 400

            current_user_email = get_jwt_identity()
            user = User.query.filter_by(email=current_user_email).first()
            if not user:
                return jsonify({"message": "User not found"}), 404

            # Create portfolio first
            valid_rows = [row for row in preview_data if row['validation_status'] == 'valid']
            portfolio = Portfolio(
                name=portfolio_name,
                user_id=user.id,
                total_holdings=len(valid_rows)
            )
            db.session.add(portfolio)
            db.session.commit()  # Commit to get portfolio ID
            print(f"Created portfolio: {portfolio_name} with ID {portfolio.id}")

            # Extract unique tickers
            tickers = list(set([row['ticker'].upper() for row in valid_rows]))

            # Fetch current prices for all tickers at once
            print(f"Fetching prices for {len(tickers)} unique securities")
            start_time = time.time()
            price_data = fetch_prices_for_portfolio(tickers)
            elapsed = time.time() - start_time
            print(
                f"Price fetching completed in {elapsed:.2f} seconds. Found prices for {len(price_data)} of {len(tickers)} securities.")

            # Now add securities with the fetched prices
            total_value = 0
            total_cost = 0
            securities_with_prices = 0

            # Process in batches to avoid large transactions
            batch_size = 50
            for i in range(0, len(valid_rows), batch_size):
                batch = valid_rows[i:i + batch_size]
                print(f"Processing batch {i // batch_size + 1} of {(len(valid_rows) + batch_size - 1) // batch_size}")

                for row in batch:
                    ticker = row['ticker'].upper()
                    current_price = 0

                    # Use fetched price if available
                    if ticker in price_data:
                        current_price = price_data[ticker]['currentPrice']
                        securities_with_prices += 1

                    # Fallback to purchase price if available and no current price
                    purchase_price = float(row.get('purchase_price', 0)) if row.get('purchase_price') else 0

                    security = Security(
                        portfolio_id=portfolio.id,
                        ticker=ticker,
                        name=row.get('name', ticker),
                        amount_owned=float(row['amount']),
                        purchase_date=datetime.strptime(row['purchase_date'], '%Y-%m-%d').date(),
                        purchase_price=purchase_price,
                        current_price=current_price,
                        sector=row.get('sector', '')
                    )

                    # Calculate values
                    security.total_value = security.amount_owned * security.current_price
                    security.value_change = 0  # Will be updated later if historical data exists
                    security.value_change_pct = 0

                    # Track totals for portfolio
                    total_value += security.total_value
                    total_cost += security.amount_owned * security.purchase_price

                    db.session.add(security)

                    if current_price > 0:
                        print(f"Added security: {security.ticker} with price: ${security.current_price}")
                    else:
                        print(f"Added security: {security.ticker} with NO PRICE")

                # Commit each batch separately
                db.session.commit()
                print(f"Committed batch {i // batch_size + 1}")

            # Update portfolio totals
            portfolio = Portfolio.query.get(portfolio.id)  # Re-fetch after commits
            portfolio.total_value = total_value
            portfolio.total_gain = total_value - total_cost
            portfolio.total_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0
            db.session.commit()
            print(f"Updated portfolio totals: value=${total_value:.2f}, gain=${portfolio.total_gain:.2f}")

            # Clean up
            try:
                file_record = PortfolioFiles.query.get(file_id)
                if file_record:
                    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file_record.filename)
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Warning: Failed to remove temporary file: {e}")
            except Exception as cleanup_error:
                print(f"Non-critical cleanup error: {cleanup_error}")

            # Report success statistics
            price_success_rate = (securities_with_prices / len(valid_rows)) * 100 if valid_rows else 0

            return jsonify({
                "message": f"Portfolio created successfully with {len(valid_rows)} securities.",
                "stats": {
                    "securities_added": len(valid_rows),
                    "securities_with_prices": securities_with_prices,
                    "price_success_rate": f"{price_success_rate:.1f}%"
                },
                "portfolio_id": portfolio.id
            }), 200

        except Exception as e:
            print(f"Error creating portfolio: {str(e)}")
            import traceback
            traceback.print_exc()
            if 'db' in locals():
                db.session.rollback()
            return jsonify({"message": f"Error creating portfolio: {str(e)}"}), 500

    except Exception as token_error:  # This is the missing block!
        print(f"Token refresh error: {str(token_error)}")
        return jsonify({"message": "Authentication error. Please log in again."}), 401


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

        # Process deletions - Now we'll delete from portfolio_securities instead
        securities_to_delete = []
        for change in changes:
            if change.get('deleted') and change.get('security_id'):
                securities_to_delete.append(change.get('security_id'))

        if securities_to_delete:
            print(f"Deleting securities from portfolio: {securities_to_delete}")

            # Convert all IDs to strings and join with commas for the SQL query
            id_list = ','.join(str(id) for id in securities_to_delete)

            # Delete from portfolio_securities instead of securities
            db.session.execute(db.text(f"""
            DELETE FROM portfolio_securities 
            WHERE id IN ({id_list}) AND portfolio_id = {portfolio_id}
            """))

            db.session.commit()
            print(f"Deleted {len(securities_to_delete)} securities from portfolio")

        # Process additions and updates through ORM
        for change in changes:
            # Skip deleted securities as they've been handled
            if change.get('deleted'):
                continue

            if change.get('new'):
                print("Adding new security:", change)

                # First find or create the security
                security = Security.query.filter_by(ticker=change['ticker']).first()

                if not security:
                    # Create the security record
                    security = Security(
                        ticker=change['ticker'],
                        name=change['name'],
                        current_price=float(change.get('current_price', 0)),
                        # Add other security fields, but not portfolio-specific ones
                    )
                    db.session.add(security)
                    db.session.flush()  # Get the ID without committing

                # Now create the portfolio-security relationship
                ps = db.session.execute(db.text("""
                INSERT INTO portfolio_securities 
                (portfolio_id, security_id, amount_owned, purchase_price, total_value, value_change, value_change_pct, total_gain, total_gain_pct)
                VALUES (:portfolio_id, :security_id, :amount, :price, :total, :change, :change_pct, :gain, :gain_pct)
                RETURNING id
                """), {
                    'portfolio_id': portfolio_id,
                    'security_id': security.id,
                    'amount': float(change['amount']),
                    'price': float(change.get('purchase_price', 0)),
                    'total': float(change.get('total_value', 0)),
                    'change': float(change.get('value_change', 0)),
                    'change_pct': float(change.get('value_change_pct', 0)),
                    'gain': float(change.get('total_gain', 0)),
                    'gain_pct': float(change.get('total_gain_pct', 0))
                })

                db.session.commit()

            elif change.get('security_id') and 'amount' in change:
                # Update amount in portfolio_securities table
                db.session.execute(db.text("""
                UPDATE portfolio_securities
                SET amount_owned = :amount,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND portfolio_id = :portfolio_id
                """), {
                    'amount': float(change['amount']),
                    'id': change.get('security_id'),
                    'portfolio_id': portfolio_id
                })

                db.session.commit()

        # Update portfolio totals using the junction table

        # Get total value from portfolio_securities
        result = db.session.execute(db.text("""
        SELECT 
            SUM(ps.total_value) as total_value,
            SUM(ps.value_change) as day_change,
            COUNT(*) as total_holdings,
            SUM(ps.total_gain) as total_gain
        FROM portfolio_securities ps
        WHERE ps.portfolio_id = :portfolio_id
        """), {'portfolio_id': portfolio_id}).fetchone()

        # Update portfolio with new totals
        total_value = result[0] or 0
        day_change = result[1] or 0
        total_holdings = result[2] or 0
        total_gain = result[3] or 0

        # Calculate percentages safely
        day_change_pct = 0
        if total_value and total_value != day_change:
            base_value = total_value - day_change
            if base_value > 0:
                day_change_pct = (day_change / base_value) * 100

        # Calculate total gain percentage from portfolio_securities
        total_gain_pct_result = db.session.execute(db.text("""
        SELECT AVG(ps.total_gain_pct) 
        FROM portfolio_securities ps
        WHERE ps.portfolio_id = :portfolio_id AND ps.total_gain_pct IS NOT NULL
        """), {'portfolio_id': portfolio_id}).fetchone()

        total_gain_pct = total_gain_pct_result[0] or 0

        # Update portfolio
        portfolio.total_value = total_value
        portfolio.day_change = day_change
        portfolio.day_change_pct = day_change_pct
        portfolio.total_holdings = total_holdings
        portfolio.total_gain = total_gain
        portfolio.total_gain_pct = total_gain_pct

        db.session.commit()

        print("Updated portfolio values:", {
            "total_value": portfolio.total_value,
            "total_holdings": portfolio.total_holdings,
            "day_change": portfolio.day_change,
            "day_change_pct": portfolio.day_change_pct,
            "total_gain": portfolio.total_gain,
            "total_gain_pct": portfolio.total_gain_pct
        })

        return jsonify({
            "message": "Portfolio updated successfully",
            "portfolio_id": portfolio_id,
            "total_value": portfolio.total_value,
            "total_holdings": portfolio.total_holdings,
            "day_change": portfolio.day_change,
            "day_change_pct": portfolio.day_change_pct,
            "total_gain": portfolio.total_gain,
            "total_gain_pct": portfolio.total_gain_pct
        }), 200

    except Exception as e:
        print(f"Error in update_portfolio: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({"message": f"Failed to update portfolio: {str(e)}"}), 500

@auth_blueprint.route('/portfolio/<int:portfolio_id>/update-prices', methods=['POST'])
@jwt_required(locations=["cookies"])
def update_portfolio_prices(portfolio_id):
    """Manually trigger a price update for a specific portfolio"""
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        # Use the price update service
        price_service = PriceUpdateService()
        result = price_service.update_prices_for_portfolio(portfolio_id)

        if result.get('success', False):
            # Format the timestamp nicely for display
            timestamp = None
            if 'timestamp' in result:
                try:
                    dt = datetime.fromisoformat(result['timestamp'])
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    timestamp = result['timestamp']

            return jsonify({
                "message": "Price update completed successfully",
                "updated_count": result.get('updated_count', 0),
                "tickers_updated": result.get('tickers_updated', []),
                "timestamp": timestamp,
                "portfolio_id": portfolio_id
            }), 200
        else:
            return jsonify({
                "message": "Price update failed",
                "error": result.get('error', 'Unknown error')
            }), 500

    except Exception as e:
        print(f"Error updating prices: {str(e)}")
        return jsonify({"message": f"Error updating prices: {str(e)}"}), 500


@auth_blueprint.route('/update-all-prices', methods=['POST'])
@jwt_required(locations=["cookies"])
def update_all_prices():
    """Manually trigger a price update for all portfolios"""
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"message": "User not found"}), 404

        # Use the price update service
        price_service = PriceUpdateService()
        result = price_service.update_all_portfolio_prices()

        if result.get('success', False):
            # Format the timestamp nicely for display
            timestamp = None
            if 'timestamp' in result:
                try:
                    dt = datetime.fromisoformat(result['timestamp'])
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    timestamp = result['timestamp']

            return jsonify({
                "message": "Price update for all portfolios completed successfully",
                "updated_count": result.get('updated_count', 0),
                "tickers_updated": result.get('tickers_updated', []),
                "elapsed_time": result.get('elapsed_time', 0),
                "timestamp": timestamp
            }), 200
        else:
            return jsonify({
                "message": "Price update failed",
                "error": result.get('error', 'Unknown error')
            }), 500

    except Exception as e:
        print(f"Error updating prices: {str(e)}")
        return jsonify({"message": f"Error updating prices: {str(e)}"}), 500


@auth_blueprint.route('/portfolio/<int:portfolio_id>/rename', methods=['POST'])
@jwt_required(locations=["cookies"])
def rename_portfolio(portfolio_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        data = request.get_json()
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({"message": "Portfolio name cannot be empty"}), 400

        portfolio.name = new_name
        db.session.commit()

        return jsonify({
            "message": "Portfolio renamed successfully",
            "portfolio_id": portfolio_id,
            "new_name": new_name
        }), 200

    except Exception as e:
        print(f"Error renaming portfolio: {str(e)}")
        db.session.rollback()
        return jsonify({"message": f"Failed to rename portfolio: {str(e)}"}), 500


# this is the risk metrics page section --------------------------------------

risk_analytics = RiskAnalytics()


@auth_blueprint.route('/api/portfolio/<int:portfolio_id>/risk', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_risk(portfolio_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()

        if not portfolio:
            return jsonify({"error": "Portfolio not found"}), 404

        # Get securities for this portfolio
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Convert securities to list of dicts with required data
        securities_data = [{
            'ticker': s.ticker,
            'total_value': s.amount_owned * s.current_price,
            'amount_owned': s.amount_owned,
            'current_price': s.current_price,
            'purchase_date': s.purchase_date.strftime("%Y-%m-%d") if s.purchase_date else None
        } for s in securities]

        # Calculate risk metrics
        risk_metrics = risk_analytics.calculate_portfolio_risk(portfolio_id, securities_data)

        # Add portfolio name to response
        risk_metrics["portfolio_name"] = portfolio.name

        return jsonify(risk_metrics)

    except Exception as e:
        print(f"Error fetching risk metrics: {str(e)}")
        return jsonify({"error": "Failed to fetch risk metrics"}), 500


@auth_blueprint.route('/risk-analysis-page', methods=['GET'])
@jwt_required(locations=["cookies"])
def risk_analysis_page():
    try:
        print("\n=== Risk Analysis Page Route ===")
        print("1. Starting route handler")

        portfolio_id = request.args.get('portfolio_id')
        print(f"2. Portfolio ID from request: {portfolio_id}")

        current_user_email = get_jwt_identity()
        print(f"3. Current user email: {current_user_email}")

        user = User.query.filter_by(email=current_user_email).first()
        print(f"4. Found user: {user is not None}")

        if not user:
            print("User not found - redirecting to login")
            return redirect(url_for('auth.login_page'))

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        print(f"5. Found portfolio: {portfolio is not None}")

        if not portfolio:
            print("Portfolio not found - redirecting to overview")
            return redirect(url_for('auth.portfolio_overview'))

        print("6. About to render template")
        try:
            result = render_template(
                'risk_analysis.html',
                user={"first_name": user.first_name, "email": user.email},
                portfolio_name=portfolio.name,
                portfolio_id=portfolio.id,
                body_class='risk-analysis-page'
            )
            print("7. Template rendered successfully")
            return result
        except Exception as template_error:
            print(f"Template rendering error: {str(template_error)}")
            raise

    except Exception as e:
        print(f"\nError in risk analysis page:")
        print(f"Type: {type(e)}")
        print(f"Error: {str(e)}")
        import traceback
        print("Traceback:")
        print(traceback.format_exc())
        return redirect(url_for('auth.portfolio_overview'))


@auth_blueprint.route('/api/portfolio-composition/<view_type>', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_composition(view_type):
    portfolio_id = request.args.get('portfolio_id')
    print(f"Received request for portfolio {portfolio_id}, view type {view_type}")

    if not portfolio_id:
        return jsonify({'error': 'Portfolio ID required'}), 400

    try:
        # Get portfolio data based on view type
        composition_data = None

        if view_type == 'sector':
            composition_data = get_sector_composition(int(portfolio_id))
        elif view_type == 'asset':
            composition_data = get_asset_composition(int(portfolio_id))
        elif view_type == 'currency':
            composition_data = get_currency_composition(int(portfolio_id))
        elif view_type == 'risk':
            composition_data = get_risk_composition(int(portfolio_id))
        else:
            return jsonify({'error': 'Invalid view type'}), 400

        if not composition_data:
            return jsonify({'error': 'No data found'}), 404

        return jsonify(composition_data)

    except Exception as e:
        print(f"Error in get_portfolio_composition: {str(e)}")  # Debug log
        return jsonify({'error': str(e)}), 500


def get_sector_composition(portfolio_id):
    """Get sector-based composition of portfolio"""
    try:
        # Query to get all securities in the portfolio with their amounts
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Initialize sector totals
        sector_totals = {}
        total_value = 0

        # Calculate value by sector
        for security in securities:
            if security.sector:  # Make sure sector exists
                value = security.amount_owned * security.current_price
                sector_totals[security.sector] = sector_totals.get(security.sector, 0) + value
                total_value += value

        # Convert to percentages
        if total_value > 0:
            sector_percentages = {
                sector: (value / total_value) * 100
                for sector, value in sector_totals.items()
            }

            # Sort by percentage descending
            sorted_sectors = sorted(sector_percentages.items(), key=lambda x: x[1], reverse=True)

            return {
                'labels': [item[0] for item in sorted_sectors],
                'values': [item[1] for item in sorted_sectors]
            }

        return {'labels': [], 'values': []}

    except Exception as e:
        print(f"Error in get_sector_composition: {str(e)}")
        return {'labels': [], 'values': []}


def get_asset_composition(portfolio_id):
    """Get asset type-based composition of portfolio"""
    try:
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Initialize asset type totals
        asset_totals = {}
        total_value = 0

        # Calculate value by asset type
        for security in securities:
            value = security.amount_owned * security.current_price
            # will want to add an asset_type field to this, but keeping with what i know
            asset_type = categorize_asset_type(security)
            asset_totals[asset_type] = asset_totals.get(asset_type, 0) + value
            total_value += value

        # Convert to percentages
        if total_value > 0:
            asset_percentages = {
                asset: (value / total_value) * 100
                for asset, value in asset_totals.items()
            }

            sorted_assets = sorted(asset_percentages.items(), key=lambda x: x[1], reverse=True)

            return {
                'labels': [item[0] for item in sorted_assets],
                'values': [item[1] for item in sorted_assets]
            }

        return {'labels': [], 'values': []}

    except Exception as e:
        print(f"Error in get_asset_composition: {str(e)}")
        return {'labels': [], 'values': []}


def get_currency_composition(portfolio_id):
    """Get currency-based composition of portfolio"""
    try:
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Initialize currency totals
        currency_totals = {}
        total_value = 0

        # Calculate value by currency
        for security in securities:
            value = security.amount_owned * security.current_price
            # For now, assuming USD as default currency will want to add a currency field later on
            currency = 'USD'
            currency_totals[currency] = currency_totals.get(currency, 0) + value
            total_value += value

        # Convert to percentages
        if total_value > 0:
            currency_percentages = {
                currency: (value / total_value) * 100
                for currency, value in currency_totals.items()
            }

            sorted_currencies = sorted(currency_percentages.items(), key=lambda x: x[1], reverse=True)

            return {
                'labels': [item[0] for item in sorted_currencies],
                'values': [item[1] for item in sorted_currencies]
            }

        return {'labels': [], 'values': []}

    except Exception as e:
        print(f"Error in get_currency_composition: {str(e)}")
        return {'labels': [], 'values': []}


def get_risk_composition(portfolio_id):
    """Get risk-based composition of portfolio"""
    try:
        securities = Security.query.filter_by(portfolio_id=portfolio_id).all()

        # Initialize risk category totals
        risk_totals = {}
        total_value = 0

        # Calculate value by risk category
        for security in securities:
            value = security.amount_owned * security.current_price
            # Categorize risk based on beta or other metrics
            risk_category = categorize_risk(security)
            risk_totals[risk_category] = risk_totals.get(risk_category, 0) + value
            total_value += value

        # Convert to percentages
        if total_value > 0:
            risk_percentages = {
                risk: (value / total_value) * 100
                for risk, value in risk_totals.items()
            }

            sorted_risks = sorted(risk_percentages.items(), key=lambda x: x[1], reverse=True)

            return {
                'labels': [item[0] for item in sorted_risks],
                'values': [item[1] for item in sorted_risks]
            }

        return {'labels': [], 'values': []}

    except Exception as e:
        print(f"Error in get_risk_composition: {str(e)}")
        return {'labels': [], 'values': []}


def categorize_asset_type(security):
    """Helper function to categorize security by asset type"""
    # super simple placeholder - just trying to get the skeleton of the risk analysis page up
    ticker = security.ticker.upper()
    if ticker.endswith('ETF'):
        return 'ETF'
    elif len(ticker) > 4:  # Simple heuristic for bonds/other securities
        return 'Bond'
    else:
        return 'Stock'


def categorize_risk(security):
    """Helper function to categorize security by risk level"""
    # This is a super simple beta example, will need to refine and make more sophisticated in the near future

    try:
        beta = float(security.beta) if hasattr(security, 'beta') and security.beta else 1.0

        if beta < 0.5:
            return 'Low Risk'
        elif beta < 1.0:
            return 'Moderate Risk'
        elif beta < 1.5:
            return 'High Risk'
        else:
            return 'Very High Risk'
    except (ValueError, AttributeError):
        return 'Uncategorized'


#  watchlist routes
@auth_blueprint.route('/watchlist', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_watchlist():
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        watchlist_items = Watchlist.query.filter_by(user_id=user.id).all()
        items = []

        for item in watchlist_items:
            # Get latest price data
            latest_price_data = (
                db.session.query(SecurityHistoricalData)
                .filter_by(ticker=item.ticker)
                .order_by(SecurityHistoricalData.date.desc())
                .first()
            )

            current_price = latest_price_data.close_price if latest_price_data else None
            previous_close = (
                db.session.query(SecurityHistoricalData)
                .filter_by(ticker=item.ticker)
                .order_by(SecurityHistoricalData.date.desc())
                .offset(1)
                .first()
            )

            items.append({
                'id': item.id,
                'ticker': item.ticker,
                'name': item.name,
                'exchange': item.exchange,
                'current_price': current_price,
                'day_change': (
                            current_price - previous_close.close_price) if current_price and previous_close else None,
                'day_change_pct': ((current_price - previous_close.close_price) / previous_close.close_price * 100)
                if current_price and previous_close else None
            })

        return jsonify(items), 200

    except Exception as e:
        print(f"Error fetching watchlist: {e}")
        return jsonify({"message": "Failed to fetch watchlist"}), 500


@auth_blueprint.route('/watchlist', methods=['POST'])
@jwt_required(locations=["cookies"])
def add_to_watchlist():
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        data = request.json
        ticker = data.get('ticker')
        name = data.get('name')
        exchange = data.get('exchange')

        # Check if already in watchlist
        existing = Watchlist.query.filter_by(user_id=user.id, ticker=ticker).first()
        if existing:
            return jsonify({"message": "Security already in watchlist", "id": existing.id}), 200

        # Try a simpler approach without specifying ID
        watchlist_item = Watchlist(
            user_id=user.id,
            ticker=ticker,
            name=name,
            exchange=exchange
        )

        try:
            db.session.add(watchlist_item)
            db.session.commit()

            return jsonify({
                "message": "Added to watchlist successfully",
                "id": watchlist_item.id
            }), 201

        except Exception as db_error:
            db.session.rollback()
            print(f"Database error adding to watchlist: {str(db_error)}")

            raw_sql = """
            INSERT INTO watchlists (user_id, ticker, name, exchange, added_at)
            VALUES (:user_id, :ticker, :name, :exchange, :added_at)
            RETURNING id
            """

            try:
                result = db.session.execute(
                    db.text(raw_sql),
                    {
                        'user_id': user.id,
                        'ticker': ticker,
                        'name': name,
                        'exchange': exchange,
                        'added_at': datetime.utcnow()
                    }
                )
                new_id = result.scalar()
                db.session.commit()

                return jsonify({
                    "message": "Added to watchlist successfully (fallback method)",
                    "id": new_id
                }), 201

            except Exception as fallback_error:
                db.session.rollback()
                print(f"Fallback error: {str(fallback_error)}")
                raise

    except Exception as e:
        print(f"Error adding to watchlist: {e}")
        db.session.rollback()
        return jsonify({"message": "Failed to add to watchlist"}), 500


@auth_blueprint.route('/watchlist/<int:item_id>', methods=['DELETE'])
@jwt_required(locations=["cookies"])
def remove_from_watchlist(item_id):
    try:
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return jsonify({"message": "User not found"}), 404

        watchlist_item = Watchlist.query.filter_by(id=item_id, user_id=user.id).first()
        if not watchlist_item:
            return jsonify({"message": "Watchlist item not found"}), 404

        db.session.delete(watchlist_item)
        db.session.commit()

        return jsonify({"message": "Removed from watchlist successfully"}), 200

    except Exception as e:
        print(f"Error removing from watchlist: {e}")
        db.session.rollback()
        return jsonify({"message": "Failed to remove from watchlist"}), 500


@auth_blueprint.route('/debug', methods=['GET'])
@jwt_required(locations=["cookies"])
def debug_view():
    """Debugging view for admins only"""
    from backend.utils.diagnostic import check_date_issues

    current_user_email = get_jwt_identity()
    user = User.query.filter_by(email=current_user_email).first()

    if not user or user.email != 'info@prophetanalytics.com':
        return jsonify({"message": "Not authorized"}), 403

    # Run diagnostics
    check_date_issues()

    # Test Alpha Vantage API directly
    import requests
    api_key = os.getenv('ALPHA_VANTAGE_KEY')

    ticker = 'AAPL'  # Test with a reliable ticker
    url = f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}"

    try:
        response = requests.get(url, timeout=10)
        api_data = response.json()

        logger = logging.getLogger('app')
        logger.info(f"API test response for {ticker}: {api_data}")

        return jsonify({
            "message": "Debug checks complete, check logs for details",
            "api_test": api_data
        })
    except Exception as e:
        return jsonify({
            "message": "Debug checks complete, but API test failed",
            "error": str(e)
        }), 500