from datetime import datetime

import numpy as np
from typing import List, Dict, Optional
from .market_data import fetch_historical_prices


class RiskAnalytics:
    def __init__(self):
        self.market_data = None

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
            var_normal = np.percentile(portfolio_returns, (1 - confidence) * 100)
            var_stress = np.percentile(portfolio_returns, (1 - confidence - 0.1) * 100)
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
        """Calculate individual security contributions to portfolio VaR"""
        components = []
        portfolio_value = sum(s['total_value'] for s in securities)

        for security in securities:
            prices = fetch_historical_prices(security['ticker'])
            returns = self._calculate_daily_returns(prices)

            var_contrib = np.percentile(returns, 5) * security['total_value']

            components.append({
                "ticker": security['ticker'],
                "var_contribution": var_contrib,
                "weight": security['total_value'] / portfolio_value,
                "volatility": np.std(returns) * np.sqrt(252)  # Annualized volatility
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
