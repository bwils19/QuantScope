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
from backend.models import PortfolioFiles, UploadedFile
from backend.services.validators import validate_ticker
from backend.services.price_update_service import PriceUpdateService
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

    return jsonify({'success': True, 'message': 'Sign up successful! Please log in.'}), 200


@auth_blueprint.route('/login', methods=['POST'])
def login():
    """Handle login form submission"""
    try:
        data = request.form
        login_id = data['login_id']  # This could be email or username
        password = data['password']
        
        # Check if input is an email or username
        is_email = '@' in login_id
        
        # Query the user based on either email or username
        if is_email:
            user = User.query.filter_by(email=login_id).first()
        else:
            user = User.query.filter_by(username=login_id).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            additional_claims = {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
            access_token = create_access_token(identity=user.email, additional_claims=additional_claims)
            csrf_token = get_csrf_token(access_token)

            # Create response with redirect
            response = make_response(redirect(url_for('auth.portfolio_overview')))

            # Set cookies
            response.set_cookie(
                'access_token_cookie',
                access_token,
                httponly=True,
                secure=False,
                samesite='Lax',
                max_age=7200
            )
            response.set_cookie(
                'csrf_access_token',
                csrf_token,
                secure=False,
                samesite='Lax',
                max_age=7200
            )
            return response

        # Invalid credentials
        if not user:
            return jsonify({
                "status": "error",
                "message": "No account found with those credentials"
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
        print("\n\n===== STARTING PORTFOLIO OVERVIEW ROUTE =====")
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()
        if not user:
            return redirect(url_for('auth.login_page'))

        # Get all portfolios for this user
        portfolios = Portfolio.query.filter_by(user_id=user.id).order_by(Portfolio.created_at.desc()).all()

        # Get all unique tickers for this user's portfolios through portfolio_securities
        unique_tickers_query = (
            db.session.query(Security.ticker)
            .join(PortfolioSecurity, Security.id == PortfolioSecurity.security_id)
            .join(Portfolio, Portfolio.id == PortfolioSecurity.portfolio_id)
            .filter(Portfolio.user_id == user.id)
            .distinct()
        )
        unique_tickers = [t[0] for t in unique_tickers_query.all()]
        print(f"Found {len(unique_tickers)} unique tickers across all portfolios")

        # Determine the most recent market date
        today = datetime.now().date()
        is_weekend = today.weekday() >= 5
        days_since_friday = today.weekday() - 4 if is_weekend else 0
        most_recent_market_date = today - timedelta(days=days_since_friday)

        # Get the most recent historical data for each ticker
        latest_prices = {}
        for ticker in unique_tickers:
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

        # Process portfolios and build the view data
        portfolio_view_data = []

        for portfolio in portfolios:
            # Get portfolio securities with their associated security data
            portfolio_securities_data = (
                db.session.query(PortfolioSecurity, Security)
                .join(Security, PortfolioSecurity.security_id == Security.id)
                .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                .all()
            )

            # Create portfolio object for the view
            portfolio_obj = {
                'id': portfolio.id,
                'name': portfolio.name,
                'user_id': portfolio.user_id,
                'created_at': portfolio.created_at,
                'updated_at': portfolio.updated_at,
                'total_holdings': portfolio.total_holdings or len(portfolio_securities_data),
                'total_value': portfolio.total_value or 0,
                'day_change': portfolio.day_change or 0,
                'day_change_pct': portfolio.day_change_pct or 0,
                'total_gain': portfolio.total_gain or 0,
                'total_gain_pct': portfolio.total_gain_pct or 0,
                'total_return': portfolio.total_return or 0,
                'total_return_pct': portfolio.total_return_pct or 0,
                'securities': []
            }

            # Recalculate portfolio totals from securities (as a fallback)
            portfolio_total_value = 0
            portfolio_day_change = 0
            portfolio_total_gain = 0

            # Add securities to the portfolio object
            for ps, security in portfolio_securities_data:
                # Use historical data if available, otherwise use current price
                latest_data = latest_prices.get(security.ticker)

                current_price = security.current_price
                previous_close = security.previous_close

                if latest_data and (not current_price or current_price == 0):
                    current_price = latest_data['current_price']
                    previous_close = latest_data['previous_close']

                # Calculate values
                total_value = ps.amount_owned * current_price
                value_change = ps.amount_owned * (current_price - previous_close) if previous_close else 0
                value_change_pct = (value_change / (
                            ps.amount_owned * previous_close)) * 100 if previous_close and previous_close > 0 else 0

                # Calculate total gain if purchase price exists
                total_gain = 0
                total_gain_pct = 0
                if ps.purchase_price:
                    total_gain = total_value - (ps.amount_owned * ps.purchase_price)
                    total_gain_pct = ((total_value / (
                                ps.amount_owned * ps.purchase_price)) - 1) * 100 if ps.purchase_price > 0 else 0

                # Add to portfolio totals
                portfolio_total_value += total_value
                portfolio_day_change += value_change
                portfolio_total_gain += total_gain

                # Create security object
                security_obj = {
                    'id': ps.id,
                    'ticker': security.ticker,
                    'name': security.name,
                    'exchange': security.exchange,
                    'amount_owned': ps.amount_owned,
                    'purchase_date': ps.purchase_date.strftime('%Y-%m-%d') if ps.purchase_date else None,
                    'purchase_price': ps.purchase_price,
                    'current_price': current_price,
                    'total_value': total_value,
                    'value_change': value_change,
                    'value_change_pct': value_change_pct,
                    'total_gain': total_gain,
                    'total_gain_pct': total_gain_pct
                }
                portfolio_obj['securities'].append(security_obj)

            # Use portfolio totals if they exist, otherwise use calculated totals
            if portfolio.total_value == 0 or portfolio.total_value is None:
                portfolio_obj['total_value'] = portfolio_total_value
                portfolio_obj['day_change'] = portfolio_day_change
                portfolio_obj['total_gain'] = portfolio_total_gain

                # Calculate percentages
                if portfolio_total_value > 0 and portfolio_day_change != 0:
                    base_value = portfolio_total_value - portfolio_day_change
                    portfolio_obj['day_change_pct'] = (portfolio_day_change / base_value) * 100 if base_value > 0 else 0

                # Calculate cost basis for total gain percentage
                cost_basis = sum([(ps.amount_owned * ps.purchase_price) for ps, _ in portfolio_securities_data if
                                  ps.purchase_price]) or 0
                if cost_basis > 0:
                    portfolio_obj['total_gain_pct'] = ((portfolio_total_value / cost_basis) - 1) * 100

            portfolio_view_data.append(portfolio_obj)

        # Debug output to help diagnose issues
        print("\n===== DEBUGGING PORTFOLIO VIEW DATA =====")
        print(f"Number of portfolio views: {len(portfolio_view_data)}")
        for i, p_view in enumerate(portfolio_view_data):
            print(f"Portfolio view {i + 1}: {p_view['name']}, ID: {p_view['id']}")
            print(f"  Total value: {p_view['total_value']}")
            print(f"  Day change: {p_view['day_change']}")
            print(f"  Number of securities: {len(p_view['securities'])}")
            for j, s in enumerate(p_view['securities'][:2]):  # Just show first 2 for brevity
                print(
                    f"    Security {j + 1}: {s['ticker']}, Amount: {s['amount_owned']}, Current price: {s['current_price']}")
                print(f"      Total value: {s['total_value']}, Day change: {s['value_change']}")
            if len(p_view['securities']) > 2:
                print(f"    ... and {len(p_view['securities']) - 2} more securities")

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

        print(f"===== PORTFOLIO OVERVIEW ROUTE COMPLETE =====")

        # adding debugging to see what is being populated when rendering the template
        for i, p in enumerate(portfolios):
            print(f"\n===== Portfolio #{i+1}: {p.name} (ID: {p.id}) =====")
            print(f"Total value: {p.total_value}")
            print(f"Day change: {p.day_change}")
            print(f"Day change %: {p.day_change_pct}")
            print(f"Total gain: {p.total_gain}")
            print(f"Total gain %: {p.total_gain_pct}")
            
            # Check the associated securities
            portfolio_securities = db.session.query(PortfolioSecurity).filter_by(portfolio_id=p.id).all()
            print(f"Number of securities: {len(portfolio_securities)}")
            
            # Calculate expected totals from securities
            total_value = 0
            total_cost = 0
            
            for ps in portfolio_securities:
                security = db.session.query(Security).filter_by(id=ps.security_id).first()
                if not security:
                    print(f"  WARNING: Missing security record for ID {ps.security_id}")
                    continue
                    
                print(f"  Security: {security.ticker}, Amount: {ps.amount_owned}, Current price: {security.current_price}")
                print(f"  Purchase price: {ps.purchase_price}, Purchase date: {ps.purchase_date}")
                
                current_value = ps.amount_owned * (security.current_price or 0)
                cost_basis = ps.amount_owned * (ps.purchase_price or 0)
                
                print(f"  Current value: {current_value}, Cost basis: {cost_basis}")
                print(f"  Gain/loss: {current_value - cost_basis}, Total gain %: {((current_value / cost_basis) - 1) * 100 if cost_basis > 0 else 0}")
                
                total_value += current_value
                total_cost += cost_basis
            
            print(f"Calculated total value: {total_value}, Stored value: {p.total_value}")
            print(f"Calculated total cost: {total_cost}")
            print(f"Calculated total gain: {total_value - total_cost}, Stored gain: {p.total_gain}")
            
            if total_cost > 0:
                calc_gain_pct = ((total_value / total_cost) - 1) * 100
                print(f"Calculated gain %: {calc_gain_pct}, Stored gain %: {p.total_gain_pct}")
            else:
                print("Cannot calculate gain % (no cost basis)")


        # Render the template with all the data
        return render_template(
            'portfolio_overview.html',
            body_class='portfolio-overview-page',
            user={"first_name": user.first_name, "email": user.email},
            portfolios=portfolio_view_data,
            dashboard_stats={
                'total_value': sum(p['total_value'] for p in portfolio_view_data),
                'day_change': sum(p['day_change'] for p in portfolio_view_data),
                'day_change_pct': (sum(p['day_change'] for p in portfolio_view_data) /
                                   (sum(p['total_value'] for p in portfolio_view_data) - sum(
                                       p['day_change'] for p in portfolio_view_data))) * 100
                if sum(p['total_value'] for p in portfolio_view_data) - sum(
                    p['day_change'] for p in portfolio_view_data) != 0 else 0,
                'total_gain': sum(p['total_gain'] for p in portfolio_view_data),
                'total_gain_pct': sum(p['total_gain_pct'] for p in portfolio_view_data) / len(
                    portfolio_view_data) if portfolio_view_data else 0
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

        # Delete portfolio_securities junction entries first
        PortfolioSecurity.query.filter_by(portfolio_id=portfolio_id).delete()

        # Now delete the portfolio
        db.session.delete(portfolio)
        db.session.commit()

        return jsonify({"message": "Portfolio deleted successfully"}), 200

    except Exception as e:
        print(f"Error deleting portfolio: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"message": f"Failed to delete portfolio: {str(e)}"}), 500


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

        # Import file validation utilities
        from backend.utils.file_validators import validate_file_security, calculate_file_hash
        
        # Perform security validation
        is_valid, validation_message = validate_file_security(file)
        if not is_valid:
            print(f"File validation failed: {validation_message}")
            return jsonify({"message": validation_message}), 400
            
        # Calculate file hash for tracking
        file_hash = calculate_file_hash(file)
        print(f"File hash: {file_hash}")
        
        # Sanitize filename
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Only allow specific file extensions
        allowed_extensions = ['.csv', '.xlsx', '.xls', '.txt']
        if file_ext not in allowed_extensions:
            print(f"Invalid file type: {file_ext}")
            return jsonify({
                "message": f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
            }), 400
            
        # Check file size (limit to 10MB)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer to beginning
        
        if file_size > 10 * 1024 * 1024:  # 10MB limit
            print(f"File too large: {file_size} bytes")
            return jsonify({
                "message": "File too large. Maximum size is 10MB."
            }), 400

        # Create a database record for the file without saving to disk
        try:
            # Try to create with new fields
            new_file = PortfolioFiles(
                user_id=user.id,
                filename=filename,
                uploaded_by=user.email,
                file_content_type=file.content_type,
                file_size=file_size
            )
            print(f"Creating database record for file with metadata")
            db.session.add(new_file)
            try:
                db.session.commit()
                print(f"File record created successfully with metadata")
            except Exception as e:
                if 'UndefinedColumn' in str(e) or 'does not exist' in str(e):
                    # Roll back and try again with original schema
                    db.session.rollback()
                    print(f"Database schema missing new columns. Using original schema.")
                    new_file = PortfolioFiles(
                        user_id=user.id,
                        filename=filename,
                        uploaded_by=user.email
                    )
                    db.session.add(new_file)
                    db.session.commit()
                    print(f"File record created successfully with original schema")
                else:
                    raise
        except Exception as e:
            if 'UndefinedColumn' in str(e) or 'does not exist' in str(e):
                # Fall back to original fields if new columns don't exist yet
                print(f"Database schema missing new columns. Using original schema.")
                new_file = PortfolioFiles(
                    user_id=user.id,
                    filename=filename,
                    uploaded_by=user.email
                )
                db.session.add(new_file)
                db.session.commit()
                print(f"File record created successfully with original schema")
            else:
                raise

        return jsonify({
            "message": f"File {filename} uploaded successfully!",
            "file_id": new_file.id
        }), 200

    except Exception as e:
        print(f"Error in upload_file: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        db.session.rollback()
        return jsonify({"message": f"Error uploading file: {str(e)}"}), 500
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

        # Create new portfolio
        portfolio = Portfolio(
            name=data["name"],
            user_id=user.id,
            total_holdings=len(stocks)
        )

        db.session.add(portfolio)
        db.session.flush()  # Get ID without committing

        total_value = 0
        total_cost = 0

        for stock in stocks:
            ticker = stock["ticker"]

            # First, get or create the security
            security = Security.query.filter_by(ticker=ticker).first()
            if not security:
                security = Security(
                    ticker=ticker,
                    name=stock["name"],
                    exchange=stock.get("exchange", "")
                    # No portfolio_id field
                )
                db.session.add(security)
                db.session.flush()  # Get ID without committing

            # Get current price data
            cache = StockCache.query.filter_by(ticker=ticker).first()
            if not cache:
                # Create placeholder pricing data
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
                db.session.flush()

            # Get price data from cache
            price_data = cache.data
            current_price = float(price_data['currentPrice'])
            amount = float(stock["amount"])

            # Update security prices if needed
            security.current_price = current_price
            security.previous_close = float(price_data.get('previousClose', current_price))

            # Create the portfolio_security relationship
            purchase_date = None
            if stock.get("purchase_date"):
                purchase_date = datetime.strptime(stock["purchase_date"], '%Y-%m-%d')

            portfolio_security = PortfolioSecurity(
                portfolio_id=portfolio.id,
                security_id=security.id,
                amount_owned=amount,
                purchase_date=purchase_date,
                purchase_price=current_price,  # Use current price as purchase price
                total_value=amount * current_price,
                value_change=float(stock['valueChange']),
                value_change_pct=float(price_data['changePercent'])
            )

            # Calculate total gain
            portfolio_security.total_gain = 0  # Initially zero since purchase price = current price
            portfolio_security.total_gain_pct = 0

            db.session.add(portfolio_security)

            # Track totals
            total_value += amount * current_price
            total_cost += amount * current_price

        # Update portfolio metrics
        portfolio.total_value = total_value
        portfolio.day_change = sum(float(s['valueChange']) for s in stocks)
        if total_value != portfolio.day_change:
            base_value = total_value - portfolio.day_change
            portfolio.day_change_pct = (portfolio.day_change / base_value) * 100 if base_value != 0 else 0

        portfolio.total_gain = total_value - total_cost
        portfolio.total_gain_pct = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0

        db.session.commit()
        price_service = PriceUpdateService()
        metrics_result = price_service.update_portfolio_metrics(portfolio.id)
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
        print(f"Error creating portfolio: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({"message": str(e)}), 500


@auth_blueprint.route('/portfolio/<int:portfolio_id>/securities', methods=['GET'])
@jwt_required(locations=["cookies"])
def get_portfolio_securities(portfolio_id):
    try:
        print(f"\n===== Loading securities for portfolio {portfolio_id} =====")
        current_user_email = get_jwt_identity()
        user = User.query.filter_by(email=current_user_email).first()

        if not user:
            return jsonify({"message": "User not found"}), 404

        portfolio = Portfolio.query.filter_by(id=portfolio_id, user_id=user.id).first()
        if not portfolio:
            return jsonify({"message": "Portfolio not found"}), 404

        # Log basic portfolio information
        print(f"Portfolio: {portfolio.name}, ID: {portfolio_id}, User: {user.email}")

        # Query portfolio securities with joined security data
        try:
            result = db.session.query(
                PortfolioSecurity,
                Security
            ).join(
                Security, PortfolioSecurity.security_id == Security.id
            ).filter(
                PortfolioSecurity.portfolio_id == portfolio_id
            ).all()
            
            print(f"Found {len(result)} securities in portfolio")
            
            # Debug info for each security
            for i, (ps, security) in enumerate(result):
                print(f"Security #{i+1}: {security.ticker} - Amount: {ps.amount_owned}, Current price: {security.current_price}")
                if security.current_price is None or security.current_price == 0:
                    print(f"WARNING: {security.ticker} has zero/null price")
        except Exception as query_error:
            print(f"Error querying portfolio securities: {str(query_error)}")
            import traceback
            print(f"Query traceback: {traceback.format_exc()}")
            return jsonify({"message": "Error querying portfolio securities"}), 500

        # Query the most recent historical data for day change calculation
        today = datetime.now().date()

        securities_data = []

        # Process each security with careful error handling
        for ps, security in result:
            try:
                # Log the processing of each security
                print(f"Processing {security.ticker} data...")
                
                # Get the most recent historical data
                latest_historical = db.session.query(SecurityHistoricalData) \
                    .filter_by(ticker=security.ticker) \
                    .order_by(SecurityHistoricalData.date.desc()) \
                    .first()

                # Get previous day historical data for day change
                previous_day_historical = None
                if latest_historical:
                    previous_day_historical = db.session.query(SecurityHistoricalData) \
                        .filter(
                        SecurityHistoricalData.ticker == security.ticker,
                        SecurityHistoricalData.date < latest_historical.date
                    ) \
                        .order_by(SecurityHistoricalData.date.desc()) \
                        .first()

                # Use historical data if available, otherwise use security current price
                latest_close = None
                close_date = None
                
                if latest_historical:
                    latest_close = latest_historical.close_price
                    close_date = latest_historical.date
                    print(f"  Found historical data: {latest_close} on {close_date}")
                elif security.current_price:
                    latest_close = security.current_price
                    print(f"  Using current price: {latest_close}")
                else:
                    print(f"  WARNING: No price data for {security.ticker}")
                    latest_close = 0  # Fallback to zero

                # Calculate day change using historical data
                previous_close = None
                day_change = 0
                day_change_pct = 0
                
                if previous_day_historical:
                    previous_close = previous_day_historical.close_price
                    print(f"  Previous close: {previous_close} on {previous_day_historical.date}")
                elif security.previous_close:
                    previous_close = security.previous_close
                    print(f"  Using stored previous close: {previous_close}")
                else:
                    previous_close = latest_close
                    print(f"  No previous close, using current: {previous_close}")
                
                if previous_close and previous_close > 0:
                    day_change = (latest_close - previous_close) * ps.amount_owned
                    day_change_pct = ((latest_close / previous_close) - 1) * 100
                
                # Create security data dictionary with safe calculations
                security_data = {
                    'id': ps.id,
                    'ticker': security.ticker,
                    'name': security.name or security.ticker,
                    'amount_owned': ps.amount_owned,
                    'current_price': security.current_price or 0,
                    'total_value': (ps.amount_owned * (security.current_price or 0)) if ps.amount_owned else 0,
                    'value_change': day_change,
                    'value_change_pct': day_change_pct,
                    'purchase_date': ps.purchase_date.strftime('%Y-%m-%d') if ps.purchase_date else None,
                    'total_gain': ps.total_gain or 0,
                    'total_gain_pct': ps.total_gain_pct or 0,
                    'latest_close': latest_close or 0,
                    'latest_close_date': close_date.strftime('%Y-%m-%d') if close_date else None
                }
                
                securities_data.append(security_data)
                print(f"  Successfully processed {security.ticker}")
                
            except Exception as sec_error:
                print(f"Error processing security {security.ticker}: {str(sec_error)}")
                import traceback
                print(f"Security traceback: {traceback.format_exc()}")
                # Skip this security but continue processing others
                continue

        # Get the latest update timestamp
        latest_update = db.session.query(func.max(SecurityHistoricalData.updated_at)).scalar()
        if not latest_update:
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

        # First, try to read CSV directly to check columns
        try:
            import pandas as pd
            file.seek(0)
            df_direct = pd.read_csv(file)
            print(f"DIRECT CSV READ - Columns: {df_direct.columns.tolist()}")
            file.seek(0)  # Reset file pointer
        except Exception as e:
            print(f"Error in direct CSV read: {str(e)}")

        # Import file validation utilities
        from backend.utils.file_validators import validate_uploaded_file, safe_read_file
        from backend.models import UploadedFile
        
        # Perform comprehensive security validation
        validation_result = validate_uploaded_file(file)
        
        if not validation_result['is_valid']:
            error_message = "; ".join(validation_result['messages'])
            print(f"File validation failed: {error_message}")
            return jsonify({"message": error_message}), 400
            
        # Get file metadata
        metadata = validation_result['metadata']
        print(f"File validated successfully: {metadata['filename']}, {metadata['size']} bytes, {metadata['mime_type']}")
        
        # Sanitize filename
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        
        # Create a record of the uploaded file with security metadata
        try:
            uploaded_file = UploadedFile.create_from_upload(
                user_id=user.id,
                file_obj=file,
                metadata=metadata
            )
            print(f"Created uploaded file record: ID {uploaded_file.id}")
        except Exception as e:
            print(f"Warning: Could not create UploadedFile record: {str(e)}")
            # Continue anyway, this is just for tracking
        
        # Get file size for database record
        file_size = metadata['size']
        file.seek(0)  # Reset file pointer to beginning

        try:
            # Process file in memory using our updated utility function
            from backend.utils.file_handlers import parse_portfolio_file
            print("parse portfolio file called======")
            
            # PATCH: If validation result contains data, use it directly
            if 'data' in validation_result and validation_result['data'] is not None:
                print("Using data from validation")
                df = validation_result['data']
                
                # Direct fix for the column name issue
                if 'amount' not in df.columns and 'amount_owned' in df.columns:
                    print("FIXING: Renaming 'amount_owned' to 'amount'")
                    df = df.rename(columns={'amount_owned': 'amount'})
                
                # Create basic validation summary if it doesn't exist
                validation_summary = {
                    'total_rows': len(df),
                    'valid_rows': len(df),  # Assume all valid initially
                    'invalid_rows': 0,
                    'total_amount': float(df['amount'].sum()) if 'amount' in df.columns else 0,
                    'unique_securities': len(df['ticker'].unique()) if 'ticker' in df.columns else 0
                }
            else:
                # Original code path
                df, validation_summary = parse_portfolio_file(file, file_ext)
                
                # Check if we still need the column fix
                if 'amount' not in df.columns and 'amount_owned' in df.columns:
                    print("FIXING AFTER PARSE: Renaming 'amount_owned' to 'amount'")
                    df = df.rename(columns={'amount_owned': 'amount'})
            
            # Validation is now handled by parse_portfolio_file function
            print(f"After processing - Columns: {df.columns.tolist()}")
            
            preview_data = format_preview_data(df)

            # Add ticker validation
            from backend.services.validators import validate_ticker

            # Validate each ticker in the preview data
            for row in preview_data:
                # Only validate if not already validated
                if row['validation_status'] != 'invalid':
                    ticker = row.get('ticker', '').strip().upper()
                    is_valid, company_name = validate_ticker(ticker)

                    if is_valid:
                        # If we have a company name and the row doesn't, use it
                        if company_name and not row.get('name'):
                            row['name'] = company_name
                        row['validation_status'] = 'valid'
                    else:
                        row['validation_status'] = 'invalid'
                        row['validation_message'] = 'Invalid ticker symbol'

            # Update validation summary based on additional validation
            valid_count = sum(1 for row in preview_data if row['validation_status'] == 'valid')
            invalid_count = len(preview_data) - valid_count
            validation_summary['valid_rows'] = valid_count
            validation_summary['invalid_rows'] = invalid_count

            # Create a record in PortfolioFiles
            # Check if the model has the new fields before using them
            try:
                # Try to create with new fields
                portfolio_file = PortfolioFiles(
                    user_id=user.id,
                    filename=filename,
                    uploaded_by=user.email,
                    file_content_type=file.content_type,
                    file_size=file_size,
                    processed=False
                )
            except Exception as e:
                if 'UndefinedColumn' in str(e) or 'does not exist' in str(e):
                    # Fall back to original fields if new columns don't exist yet
                    print("Warning: New columns not available in database. Using original schema.")
                    portfolio_file = PortfolioFiles(
                        user_id=user.id,
                        filename=filename,
                        uploaded_by=user.email
                    )
                else:
                    raise
            db.session.add(portfolio_file)
            db.session.commit()

            # Store the preview data in the session for later use
            from flask import session
            session[f'preview_data_{portfolio_file.id}'] = preview_data
            
            return jsonify({
                'preview_data': preview_data,
                'summary': validation_summary,
                'message': 'File processed successfully',
                'file_id': portfolio_file.id
            })

        except Exception as e:
            print(f"Error processing file: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return jsonify({
                'message': f"Error processing file: {str(e)}"
            }), 500

    except Exception as e:
        print(f"Error in preview: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            'message': f"Error processing file: {str(e)}"
        }), 500


@auth_blueprint.route('/create-portfolio-from-file/<int:file_id>', methods=['POST'])
@jwt_required(locations=["cookies"])
def create_portfolio_from_file(file_id):
    """Create a portfolio from an uploaded file with enhanced security validation"""
    try:
        # Log the request for audit purposes
        current_user_email = get_jwt_identity()
        print(f"Portfolio creation from file {file_id} requested by {current_user_email}")
        
        # Check if the file exists in the UploadedFile table for security tracking
        from backend.models import UploadedFile
        uploaded_file = UploadedFile.query.filter_by(id=file_id).first()
        
        if uploaded_file:
            # Verify the file belongs to the current user
            if uploaded_file.user_id != User.query.filter_by(email=current_user_email).first().id:
                print(f"Security warning: User {current_user_email} attempted to access file {file_id} belonging to user {uploaded_file.user_id}")
                return jsonify({"message": "Access denied: You do not have permission to use this file"}), 403
                
            # Update the file status to indicate it's being processed
            uploaded_file.status = 'processing'
            uploaded_file.is_processed = True
            uploaded_file.processed_date = datetime.utcnow()
            db.session.commit()
            
            print(f"Processing validated file: {uploaded_file.original_filename} ({uploaded_file.mime_type})")
        else:
            # Fall back to the old PortfolioFiles table if the file is not in the new table
            portfolio_file = PortfolioFiles.query.get(file_id)
            if not portfolio_file:
                print(f"Warning: File {file_id} not found in either UploadedFile or PortfolioFiles tables")
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
                
            # Get preview data from session if not provided in request
            from flask import session
            if not preview_data and f'preview_data_{file_id}' in session:
                preview_data = session.get(f'preview_data_{file_id}')
                # Clear session data after retrieving
                session.pop(f'preview_data_{file_id}', None)

            if not preview_data:
                return jsonify({"message": "No preview data found. Please upload the file again."}), 400

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

            # Now add securities with the fetched prices
            total_value = 0
            total_cost = 0
            securities_with_prices = 0

            # Process in batches to avoid large transactions, this shit keeps crashing...
            batch_size = 50
            for i in range(0, len(valid_rows), batch_size):
                batch = valid_rows[i:i + batch_size]
                print(f"Processing batch {i // batch_size + 1} of {(len(valid_rows) + batch_size - 1) // batch_size}")

                for row in batch:
                    ticker = row['ticker'].upper()

                    # First find or create the Security record
                    security = Security.query.filter_by(ticker=ticker).first()

                    if not security:
                        # Create a new Security (without portfolio_id)
                        security = Security(
                            ticker=ticker,
                            name=row.get('name', ticker),
                            exchange=row.get('exchange', '')
                            # No portfolio_id field anymore
                        )
                        db.session.add(security)
                        db.session.flush()  # Get the ID without committing

                    # Get or calculate prices
                    current_price = 0
                    purchase_price = float(row.get('purchase_price', 0)) if row.get('purchase_price') else 0

                    # Check StockCache for current price
                    cache = StockCache.query.filter_by(ticker=ticker).first()
                    if cache and cache.data:
                        current_price = cache.data.get('currentPrice', 0)
                        previous_close = cache.data.get('previousClose', current_price)
                        securities_with_prices += 1

                        # If no price, use purchase price as fallback
                        if current_price == 0 and purchase_price > 0:
                            current_price = purchase_price

                        # Update security price if there is one
                        if current_price > 0:
                            security.current_price = current_price
                            security.previous_close = previous_close
                    else:
                        # If no cache data, try to get from historical data
                        historical_data = db.session.query(SecurityHistoricalData) \
                            .filter(SecurityHistoricalData.ticker == ticker) \
                            .order_by(SecurityHistoricalData.date.desc()) \
                            .limit(2) \
                            .all()

                        if len(historical_data) >= 2:
                            # Use the most recent day for current_price and the day before for previous_close
                            current_price = historical_data[0].close_price
                            previous_close = historical_data[1].close_price

                            # Update the security
                            security.current_price = current_price
                            security.previous_close = previous_close
                        elif len(historical_data) == 1:
                            # If only one day of data, use it for both
                            current_price = historical_data[0].close_price
                            previous_close = current_price

                            security.current_price = current_price
                            security.previous_close = previous_close
                        elif purchase_price > 0:
                            # If no historical data but we have purchase price, use it
                            current_price = purchase_price
                            previous_close = purchase_price

                            security.current_price = current_price
                            security.previous_close = previous_close

                    # Create the PortfolioSecurity entry (the junction table record)
                    amount = float(row['amount'])
                    purchase_date = datetime.strptime(row['purchase_date'], '%Y-%m-%d').date()

                    portfolio_security = PortfolioSecurity(
                        portfolio_id=portfolio.id,
                        security_id=security.id,
                        amount_owned=amount,
                        purchase_date=purchase_date,
                        purchase_price=purchase_price,
                        total_value=amount * current_price,
                        value_change=0,  # Will be calculated later
                        value_change_pct=0,
                        total_gain=amount * current_price - amount * purchase_price if purchase_price > 0 else 0,
                        total_gain_pct=((current_price / purchase_price) - 1) * 100 if purchase_price > 0 else 0
                    )

                    db.session.add(portfolio_security)

                    # Track totals for portfolio
                    total_value += amount * current_price
                    total_cost += amount * purchase_price

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

            # Update file status in both tables for backward compatibility
            try:
                # First try the new UploadedFile table
                uploaded_file = UploadedFile.query.filter_by(id=file_id).first()
                if uploaded_file:
                    uploaded_file.status = 'completed'
                    uploaded_file.is_processed = True
                    uploaded_file.processed_date = datetime.utcnow()
                    uploaded_file.metadata = {
                        **(uploaded_file.metadata or {}),
                        'portfolio_id': portfolio.id,
                        'securities_count': len(valid_rows),
                        'completion_time': datetime.utcnow().isoformat()
                    }
                    db.session.commit()
                    print(f"Updated UploadedFile record {file_id} with status 'completed'")
                
                # Also try the old PortfolioFiles table for backward compatibility
                file_record = PortfolioFiles.query.get(file_id)
                if file_record:
                    try:
                        # Try to set the processed flag
                        file_record.processed = True
                        db.session.commit()
                    except Exception as e:
                        # If the processed column doesn't exist, just ignore it
                        if 'UndefinedColumn' in str(e) or 'does not exist' in str(e):
                            print(f"Warning: 'processed' column not available in database. Skipping update.")
                            db.session.rollback()
                        else:
                            raise
            except Exception as cleanup_error:
                print(f"Non-critical error updating file record: {cleanup_error}")
                db.session.rollback()

            # Report success statistics
            price_success_rate = (securities_with_prices / len(valid_rows)) * 100 if valid_rows else 0
            
            # Log the successful portfolio creation for audit purposes
            print(f"Portfolio {portfolio.id} created successfully from file {file_id} by user {current_user_email}")
            
            # Ensure portfolio metrics are properly calculated
            try:
                print(f"Calculating portfolio metrics for portfolio {portfolio.id}...")
                price_service = PriceUpdateService()
                
                # Force update of all securities in the portfolio to ensure current prices
                securities_update = price_service.update_prices_for_portfolio(portfolio.id)
                if not securities_update.get('success', False):
                    print(f"Warning: Failed to update security prices: {securities_update.get('error', 'Unknown error')}")
                
                # Now update all portfolio metrics
                metrics_result = price_service.update_portfolio_metrics(portfolio.id)
                
                if metrics_result.get('success', False):
                    print(f"Portfolio metrics updated successfully:")
                    print(f"  Total value: ${metrics_result.get('total_value', 0):.2f}")
                    print(f"  Day change: ${metrics_result.get('day_change', 0):.2f}")
                    print(f"  Total gain: ${metrics_result.get('total_gain', 0):.2f}")
                    print(f"  Total return: ${metrics_result.get('total_return', 0):.2f}")
                else:
                    print(f"Warning: Failed to update portfolio metrics: {metrics_result.get('error', 'Unknown error')}")
                    
                    # Fallback: Calculate basic metrics directly
                    print("Attempting direct calculation of portfolio metrics...")
                    portfolio = Portfolio.query.get(portfolio.id)  # Re-fetch portfolio
                    
                    # Calculate day change based on current and previous prices
                    day_change = 0
                    portfolio_securities = (
                        db.session.query(PortfolioSecurity, Security)
                        .join(Security, PortfolioSecurity.security_id == Security.id)
                        .filter(PortfolioSecurity.portfolio_id == portfolio.id)
                        .all()
                    )
                    
                    for ps, security in portfolio_securities:
                        current_price = security.current_price or 0
                        previous_close = security.previous_close or current_price
                        day_change += ps.amount_owned * (current_price - previous_close)
                    
                    # Update portfolio with calculated values
                    portfolio.day_change = day_change
                    portfolio.day_change_pct = (day_change / (portfolio.total_value - day_change)) * 100 if portfolio.total_value > day_change else 0
                    db.session.commit()
                    portfolio = Portfolio.query.get(portfolio.id)

                    
                    print(f"Direct calculation complete. Day change: ${day_change:.2f}")
            except Exception as metrics_error:
                print(f"Error calculating portfolio metrics: {str(metrics_error)}")
                import traceback
                traceback.print_exc()

            try:
                svc = PriceUpdateService(session=db.session)
                svc.update_prices_for_portfolio(portfolio.id)
                svc.update_portfolio_metrics(portfolio.id)
            except Exception as price_exc:
                current_app.logger.error(
                    f"Sync price‐update failed (but portfolio is created): {price_exc}",
                    exc_info=True
                )

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

    except Exception as token_error:
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

        price_service = PriceUpdateService()
        metrics_result = price_service.update_portfolio_metrics(portfolio_id)

        if not metrics_result.get('success', False):
            print(f"Warning: Failed to update portfolio metrics: {metrics_result.get('error')}")

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

            # Get the updated portfolio to include total return in the response
            updated_portfolio = Portfolio.query.get(portfolio_id)
            
            return jsonify({
                "message": "Price update completed successfully",
                "updated_count": result.get('updated_count', 0),
                "tickers_updated": result.get('tickers_updated', []),
                "timestamp": timestamp,
                "portfolio_id": portfolio_id,
                "total_value": updated_portfolio.total_value,
                "day_change": updated_portfolio.day_change,
                "total_gain": updated_portfolio.total_gain,
                "total_return": updated_portfolio.total_return,
                "total_return_pct": updated_portfolio.total_return_pct
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

            # Get summary of updated portfolios
            portfolios = Portfolio.query.filter_by(user_id=user.id).all()
            portfolio_summaries = []
            
            for portfolio in portfolios:
                portfolio_summaries.append({
                    "id": portfolio.id,
                    "name": portfolio.name,
                    "total_value": portfolio.total_value,
                    "day_change": portfolio.day_change,
                    "total_gain": portfolio.total_gain,
                    "total_return": portfolio.total_return,
                    "total_return_pct": portfolio.total_return_pct
                })
            
            return jsonify({
                "message": "Price update for all portfolios completed successfully",
                "updated_count": result.get('updated_count', 0),
                "tickers_updated": result.get('tickers_updated', []),
                "elapsed_time": result.get('elapsed_time', 0),
                "timestamp": timestamp,
                "portfolios": portfolio_summaries
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

        # Check if benchmark data exists
        try:
            benchmark_ticker = 'SPY'  # S&P 500 ETF
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=252)  # One year lookback
            
            benchmark_data = db.session.query(SecurityHistoricalData).filter(
                SecurityHistoricalData.ticker == benchmark_ticker,
                SecurityHistoricalData.date >= start_date,
                SecurityHistoricalData.date <= end_date
            ).order_by(SecurityHistoricalData.date.desc()).first()
            
            if not benchmark_data:
                print(f"WARNING: No recent benchmark data found for {benchmark_ticker}")
                # Check if any data exists at all
                any_benchmark = db.session.query(SecurityHistoricalData).filter(
                    SecurityHistoricalData.ticker == benchmark_ticker
                ).first()
                
                if any_benchmark:
                    print(f"Some benchmark data exists, but not in the required date range")
                else:
                    print(f"No benchmark data exists at all - beta calculation will fail")
        except Exception as e:
            print(f"Error checking benchmark data: {str(e)}")

        # Get portfolio securities with their associated security data
        # This needs to use the junction table
        portfolio_securities = (
            db.session.query(PortfolioSecurity, Security)
            .join(Security, PortfolioSecurity.security_id == Security.id)
            .filter(PortfolioSecurity.portfolio_id == portfolio_id)
            .all()
        )

        # Convert securities to list of dicts with required data
        securities_data = []
        for ps, security in portfolio_securities:
            security_data = {
                'ticker': security.ticker,
                'amount_owned': ps.amount_owned,
                'purchase_date': ps.purchase_date.strftime("%Y-%m-%d") if ps.purchase_date else None,
                'current_price': security.current_price,
                'total_value': ps.total_value
            }
            securities_data.append(security_data)

        # Add detailed logging for securities data
        print("\n===== DEBUG: Securities Data for Beta Calculation =====")
        print(f"Number of securities: {len(securities_data)}")
        for sec in securities_data[:2]:  # Print first two for brevity
            print(f"Security details: {sec}")
        print("=====")

        # Diagnose beta calculation before attempting it
        beta_diagnostics = risk_analytics.diagnose_beta_calculation(securities_data)
        print(f"Beta diagnostics: {beta_diagnostics}")

        # Calculate risk metrics
        risk_metrics = risk_analytics.calculate_portfolio_risk(portfolio_id, securities_data)

        # Add portfolio name to response
        risk_metrics["portfolio_name"] = portfolio.name

        return jsonify(risk_metrics)

    except Exception as e:
        print(f"Error fetching risk metrics: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
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