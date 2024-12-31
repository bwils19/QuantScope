from backend import db
from datetime import datetime


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


# class Portfolio(db.Model):
#     __tablename__ = 'portfolio'
#
#     id = db.Column(db.Integer, primary_key=True)
#     user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
#     name = db.Column(db.String(255), nullable=False)
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
#     total_holdings = db.Column(db.Integer, default=0)
#
#     # Relationship
#     user = db.relationship('User', backref=db.backref('portfolios', lazy=True))
#
#     def __repr__(self):
#         return f'<Portfolio {self.name}>'


class PortfolioSecurity(db.Model):
    __tablename__ = 'portfolio_security'

    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'))
    ticker = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    industry = db.Column(db.String(255), nullable=True)
    shares = db.Column(db.Float, nullable=False)
    value_change = db.Column(db.Float, nullable=True)  # Placeholder for day change
    gain_loss = db.Column(db.Float, nullable=True)  # Placeholder for gain/loss (1Y)
    return_1y = db.Column(db.Float, nullable=True)  # Placeholder for return (1Y)

    portfolio = db.relationship('Portfolio', backref=db.backref('securities', lazy=True))


class StockCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticker = db.Column(db.String(10), nullable=False, unique=True)
    date = db.Column(db.Date, nullable=False)
    data = db.Column(db.JSON, nullable=False)  # Store the full JSON response here
    updated_at = db.Column(db.DateTime, default=db.func.now())


class PortfolioFiles(db.Model):
    __tablename__ = 'portfolio_files'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    uploaded_by = db.Column(db.String(255), nullable=False)

    user = db.relationship('User', backref=db.backref('portfolio_files', lazy=True))


class Portfolio(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Security(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('portfolio.id'), nullable=False)
    ticker = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    exchange = db.Column(db.String(10))
    asset_type = db.Column(db.String(20))
    amount_owned = db.Column(db.Float, nullable=False)
    value_change = db.Column(db.Float, default=0.0)
    total_value = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
