from datetime import datetime

import numpy as np
from typing import List, Dict, Optional
from .market_data import fetch_historical_prices


def calculate_credit_risk(securities_data):
    """ Placeholder method for credit risk.
        Could be refined to look up credit spreads,
        bond durations, or default probabilities.
    """
    total_credit_risk = 0
    for s in securities_data:
        # Placeholder logic:
        # Suppose each security that is a bond has a small credit risk measure
        # or just return 0 for everything as a placeholder
        pass

    return {
        "cs01": 0.0  # or some real measure
    }


def calculate_portfolio_beta(self, securities_data, portfolio_value):
    """ Calculate portfolio beta as weighted average of individual betas.
        This requires a way to fetch each security's beta or compute it.
        Putting this on hold until I get VaR incorporated completely
    """
    total_beta = 0
    for s in securities_data:
        # You'd need each security's beta from some source
        # e.g., yahoo finance or your own historical regression
        # For now, let's pretend we have a function get_beta(ticker)
        beta_of_security = self._get_beta_for_ticker(s['ticker'])
        weight = s['total_value'] / portfolio_value if portfolio_value else 0
        total_beta += beta_of_security * weight

    return total_beta


def _get_beta_for_ticker(self, ticker):
    # Placeholder or fetch from an API
    # e.g., return 1.2 for AAPL, etc.
    return 1.0


class RiskAnalytics:
    def __init__(self):
        self.market_data = None

    def calculate_portfolio_risk(self, portfolio_id: int, securities: List[Dict]) -> Dict:
        """Calculate comprehensive portfolio risk metrics"""
        portfolio_value = sum(s['total_value'] for s in securities)

        # Calculate VaR metrics
        var_metrics = self.calculate_dynamic_var(securities)

        # Calculate component risks
        var_components = self.get_var_components(securities)

        # Calculate portfolio beta
        beta = self.calculate_portfolio_beta(securities, portfolio_value)

        # Calculate credit risk
        credit_risk = self.calculate_credit_risk(securities)

        return {
            "total_value": portfolio_value,
            "beta": beta,
            "var_metrics": var_metrics,
            "var_components": var_components,
            "credit_risk": credit_risk
        }

    def calculate_portfolio_beta(self, securities: List[Dict], portfolio_value: float) -> float:
        """Calculate portfolio beta as weighted average of individual betas"""
        if not portfolio_value:
            return 0.0

        total_beta = 0.0
        for security in securities:
            weight = security['total_value'] / portfolio_value
            # For now using a simple beta of 1.0, but you could fetch real betas
            beta = self._get_beta_for_ticker(security['ticker'])
            total_beta += beta * weight

        return total_beta

    def calculate_credit_risk(self, securities: List[Dict]) -> Dict:
        """Calculate portfolio credit risk metrics"""
        total_cs01 = 0.0
        total_value = sum(s['total_value'] for s in securities)

        for security in securities:
            # Simple placeholder - you might want to refine this based on security type
            weight = security['total_value'] / total_value if total_value else 0
            total_cs01 += weight * 0.0001  # 1bp sensitivity

        return {
            "cs01": total_cs01,
            "total_exposure": total_value
        }

    def _get_beta_for_ticker(self, ticker: str) -> float:
        """Get beta for a given ticker - placeholder for now"""
        # You could enhance this to fetch real betas from your data source
        return 1.0

    def calculate_dynamic_var(self, securities: List[Dict], confidence: float = 0.95) -> Dict:
        """Calculate VaR with dynamic market regime detection, accounting for purchase dates."""
        portfolio_value = sum(s['total_value'] for s in securities)

        # Handle empty portfolio
        if not portfolio_value or not securities:
            return {
                "var_normal": 0,
                "var_stress": 0,
                "cvar": 0,
                "regime_distribution": {"normal": 1, "stress": 0}
            }

        historical_returns = []

        for security in securities:
            try:
                # Fetch prices and align to purchase date
                prices = fetch_historical_prices(security['ticker'])
                purchase_date = datetime.strptime(security['purchase_date'], "%Y-%m-%d")
                filtered_prices = [price for date, price in prices if date >= purchase_date]

                if len(filtered_prices) < 2:
                    continue

                returns = self._calculate_daily_returns(filtered_prices)

                if len(returns) > 0:
                    # Dynamically adjust weight for valid periods
                    weight = security['total_value'] / portfolio_value
                    weighted_returns = returns * weight
                    historical_returns.append(weighted_returns)
            except Exception as e:
                print(f"Error processing {security['ticker']}: {str(e)}")
                continue

        if not historical_returns:
            return {
                "var_normal": portfolio_value * 0.05,  # Conservative estimate
                "var_stress": portfolio_value * 0.08,
                "cvar": portfolio_value * 0.10,
                "regime_distribution": {"normal": 1, "stress": 0}
            }

        # Combine weighted returns to simulate portfolio behavior
        portfolio_returns = np.sum(historical_returns, axis=0)

        if len(portfolio_returns) > 0:
            var_normal_conf = 0.95
            var_stress_conf = 0.99  # i could up this to 0.995 for more extreme stress. this is good for now...

            var_normal = np.percentile(portfolio_returns, (1 - var_normal_conf) * 100)
            var_stress = np.percentile(portfolio_returns, (1 - var_stress_conf) * 100)
            tail_returns = portfolio_returns[portfolio_returns <= var_normal]
            cvar = np.mean(tail_returns) if len(tail_returns) > 0 else var_normal
        else:
            var_normal = -0.05
            var_stress = -0.08
            cvar = -0.10

        return {
            "var_normal": var_normal * portfolio_value,
            "var_stress": var_stress * portfolio_value,
            "cvar": cvar * portfolio_value,
            "regime_distribution": {
                "normal": 0.8,
                "stress": 0.2
            }
        }

    def get_var_components(self, securities: List[Dict]) -> List[Dict]:
        components = []
        portfolio_value = sum(s['total_value'] for s in securities)

        for security in securities:
            # Fetch (date, price) pairs
            all_data = fetch_historical_prices(security['ticker'])
            # Extract just the price floats
            price_series = [p for (d, p) in all_data]

            returns = self._calculate_daily_returns(price_series)

            if len(returns) == 0:
                # handle the case where there's no usable data? - need to figure that out.
                # for now set var_contrib = 0
                var_contrib = 0
            else:
                # 5th percentile of returns (which is the same as 95% confidence if you interpret negative tail)
                var_contrib = np.percentile(returns, 5) * security['total_value']

            components.append({
                "ticker": security['ticker'],
                "var_contribution": var_contrib,
                "weight": security['total_value'] / portfolio_value if portfolio_value else 0,
                "volatility": np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
            })

        return components

    @staticmethod
    def _calculate_daily_returns(prices: np.ndarray) -> np.ndarray:
        """Calculate daily returns from price series"""
        if len(prices) < 2:
            return np.array([])
        # Calculate percentage returns: (P_t - P_t-1) / P_t-1
        returns = np.diff(prices) / prices[:-1]
        # Remove infinite values and NaNs
        returns = returns[np.isfinite(returns)]
        return returns
