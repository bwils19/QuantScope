from typing import Dict, Optional

from backend import db
from datetime import datetime, timedelta


class User(db.Model):
    __tablename__ = 'users'  # Changed to match foreign key references
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class Portfolio(db.Model):
    __tablename__ = 'portfolios'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Portfolio metrics
    total_holdings = db.Column(db.Integer, default=0)  # Number of different securities
    total_value = db.Column(db.Float, default=0.0)  # Current total value
    day_change = db.Column(db.Float, default=0.0)  # Daily value change
    day_change_pct = db.Column(db.Float, default=0.0)  # Daily percentage change
    total_gain = db.Column(db.Float, default=0.0)  # Total gain/loss across all positions
    total_gain_pct = db.Column(db.Float, default=0.0)
    total_return = db.Column(db.Float, default=0.0)  # Total return including closed positions
    total_return_pct = db.Column(db.Float, default=0.0)  # Total return percentage

    # Relationships
    securities = db.relationship('Security', backref='portfolio', cascade='all, delete-orphan')
    user = db.relationship('User', backref=db.backref('portfolios', lazy=True))


class Security(db.Model):
    __tablename__ = 'securities'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'), nullable=False)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    exchange = db.Column(db.String(50))

    # Additional categorization fields
    asset_type = db.Column(db.String(50), default='Equity')
    sector = db.Column(db.String(50), nullable=True)
    currency = db.Column(db.String(3), default='USD')

    # Position information
    amount_owned = db.Column(db.Float, nullable=False)
    purchase_price = db.Column(db.Float)
    purchase_date = db.Column(db.Date, nullable=True)
    current_price = db.Column(db.Float)
    total_value = db.Column(db.Float)

    # Performance metrics
    value_change = db.Column(db.Float)
    value_change_pct = db.Column(db.Float)
    total_gain = db.Column(db.Float)  # total gain/loss in dollars since purchase
    total_gain_pct = db.Column(db.Float)

    # Timestamps
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    historical_data = db.relationship(
        'SecurityHistoricalData',
        primaryjoin="Security.ticker==SecurityHistoricalData.ticker",
        foreign_keys="SecurityHistoricalData.ticker",
        cascade="all, delete",
        backref=db.backref('security', lazy=True),
        viewonly=True
    )


class SecurityHistoricalData(db.Model):
    __tablename__ = 'security_historical_data'
    __table_args__ = (
        db.UniqueConstraint('ticker', 'date', name='uix_ticker_date'),
        db.Index('idx_security_date', 'ticker', 'date'),
        {'extend_existing': True}
    )

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    open_price = db.Column(db.Float)
    high_price = db.Column(db.Float)
    low_price = db.Column(db.Float)
    close_price = db.Column(db.Float)
    adjusted_close = db.Column(db.Float)
    volume = db.Column(db.BigInteger)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('ticker', 'date', name='uix_ticker_date'),
        db.Index('idx_security_date', 'ticker', 'date')
    )

    security = db.relationship('Security',
                               primaryjoin="SecurityHistoricalData.ticker==Security.ticker",
                               foreign_keys=[ticker],
                               backref=db.backref('historical_data', lazy='dynamic'))


class StockCache(db.Model):
    __tablename__ = 'stock_cache'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, unique=True, index=True)
    date = db.Column(db.Date, nullable=False)
    data = db.Column(db.JSON)

    @property
    def current_price(self):
        return self.data.get('currentPrice') if self.data else None

    @property
    def previous_close(self):
        return self.data.get('previousClose') if self.data else None

    @property
    def change_percent(self):
        return self.data.get('changePercent') if self.data else None


class PortfolioFiles(db.Model):
    __tablename__ = 'portfolio_files'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    uploaded_by = db.Column(db.String(255), nullable=False)

    user = db.relationship('User', backref=db.backref('portfolio_files', lazy=True))


# log the historical updates so i can keep track of when this works and not.
class HistoricalDataUpdateLog(db.Model):
    __tablename__ = 'historical_data_update_log'
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, primary_key=True)
    update_time = db.Column(db.DateTime, default=datetime.utcnow)
    tickers_updated = db.Column(db.Integer)
    records_added = db.Column(db.Integer)
    status = db.Column(db.String(50))
    error = db.Column(db.Text, nullable=True)


class Watchlist(db.Model):
    __tablename__ = 'watchlists'
    __table_args__ = {'extend_existing': True}
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ticker = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    exchange = db.Column(db.String(50))
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship with User
    user = db.relationship('User', backref=db.backref('watchlist_items', lazy=True))


class SecurityMetadata(db.Model):
    __tablename__ = 'security_metadata'

    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), unique=True, nullable=False)
    sector = db.Column(db.String(100))
    industry = db.Column(db.String(100))
    asset_type = db.Column(db.String(50))
    currency = db.Column(db.String(3))
    exchange = db.Column(db.String(20))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SecurityMetadata {self.ticker}>'


class RiskAnalysisCache(db.Model):
    __tablename__ = 'risk_analysis_cache'

    # Change how ID is defined to better handle sequence issues
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolios.id'), unique=True)
    cache_data = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

    # Add relationship
    portfolio = db.relationship('Portfolio', backref=db.backref('risk_cache', lazy=True))

    @classmethod
    def get_cache(cls, portfolio_id: int) -> Optional[Dict]:
        try:
            cache = cls.query.filter_by(portfolio_id=portfolio_id).first()
            if not cache or cache.expires_at < datetime.utcnow():
                return None
            return cache.cache_data
        except Exception as e:
            print(f"Error retrieving cache: {str(e)}")
            return None

    @classmethod
    def set_cache(cls, portfolio_id: int, data: Dict, ttl: timedelta = None):
        ttl = ttl or timedelta(hours=24)
        try:
            # Try to update existing record first
            cache = cls.query.filter_by(portfolio_id=portfolio_id).first()

            if cache:
                cache.cache_data = data
                cache.expires_at = datetime.utcnow() + ttl
                cache.created_at = datetime.utcnow()
            else:
                # Create new record
                cache = cls(
                    portfolio_id=portfolio_id,
                    cache_data=data,
                    expires_at=datetime.utcnow() + ttl
                )
                db.session.add(cache)

            db.session.commit()

        except Exception as e:
            db.session.rollback()
            print(f"Error setting cache: {str(e)}")


class StressScenario(db.Model):
    __tablename__ = 'stress_scenarios'
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(50), nullable=False)
    index_name = db.Column(db.String(50), nullable=False)
    price_change_pct = db.Column(db.Float)
    volatility = db.Column(db.Float)
    vix_shift_pct = db.Column(db.Float)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)

    def __repr__(self):
        return f"<StressScenario {self.event_name} - {self.index_name}>"
