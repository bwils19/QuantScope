import numpy as np
from typing import List, Dict, Optional
from .market_data import fetch_historical_prices, fetch_credit_spread_data, fetch_market_data


class RiskAnalytics:
    def __init__(self):
        self.market_data = None

    def calculate_var(self, securities: List[Dict], confidence: float = 0.95) -> float:
        """Calculate Value at Risk for a portfolio"""
        historical_returns = []

        for security in securities:
            historical_prices = fetch_historical_prices(security['ticker'])
            returns = self._calculate_daily_returns(historical_prices)
            weighted_returns = returns * security['amount_owned']
            historical_returns.append(weighted_returns)

        portfolio_returns = np.sum(historical_returns, axis=0)
        var = np.percentile(portfolio_returns, (1 - confidence) * 100)
        return var

    def calculate_credit_risk(self, securities: List[Dict]) -> Dict:
        """Calculate credit risk metrics"""
        total_cs01 = 0
        security_details = []

        for security in securities:
            spread_data = fetch_credit_spread_data(security['ticker'])
            security_cs01 = self._calculate_security_cs01(
                spread_data,
                security['amount_owned'],
                security['current_price']
            )
            total_cs01 += security_cs01
            security_details.append({
                'ticker': security['ticker'],
                'cs01': security_cs01
            })

        return {
            'total_cs01': total_cs01,
            'security_details': security_details
        }

    def calculate_portfolio_beta(self, securities: List[Dict], portfolio_value: float) -> float:
        """Calculate portfolio beta"""
        if self.market_data is None:
            self.market_data = fetch_market_data()

        portfolio_beta = 0

        for security in securities:
            security_data = fetch_historical_prices(security['ticker'])
            security_beta = self._calculate_security_beta(security_data, self.market_data)
            weight = security['total_value'] / portfolio_value
            portfolio_beta += security_beta * weight

        return portfolio_beta

    @staticmethod
    def _calculate_daily_returns(prices: np.ndarray) -> np.ndarray:
        """Calculate daily returns from price series"""
        return np.diff(prices) / prices[:-1]

    @staticmethod
    def _calculate_security_beta(security_returns: np.ndarray,
                                 market_returns: np.ndarray) -> float:
        """Calculate beta using covariance method"""
        covariance = np.cov(security_returns, market_returns)[0][1]
        market_variance = np.var(market_returns)
        return covariance / market_variance
