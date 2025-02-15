from datetime import datetime

import numpy as np
from typing import List, Dict, Optional, Tuple, Any
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
        self.RISK_FREE_RATE = 0.05  # 5% annual rate - should be fetched from market data
        self.VAR_HORIZON = 10  # 10-day VaR
        self.TRADING_DAYS = 252  # Number of trading days in a year

    def calculate_portfolio_risk(self, portfolio_id: int, securities: List[Dict]) -> Dict:
        """Calculate comprehensive portfolio risk metrics"""
        portfolio_value = sum(s['total_value'] for s in securities)

        # Calculate VaR metrics with scaling
        var_metrics = self.calculate_dynamic_var(securities)

        # Calculate component risks with correlation adjustments
        var_components = self.get_var_components(securities)

        # Calculate portfolio beta against market index
        beta = self.calculate_portfolio_beta(securities, portfolio_value)

        # Calculate credit risk metrics
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
        """
        Calculate VaR with dynamic market regime detection and proper time scaling.

        Parameters:
        - securities: List of security dictionaries
        - confidence: Confidence level (default 95%)

        Returns:
        - Dictionary containing VaR metrics and regime information
        """
        portfolio_value = sum(s['total_value'] for s in securities)

        if not portfolio_value or not securities:
            return self._get_default_var_metrics(portfolio_value)

        historical_returns = []
        weights = []

        for security in securities:
            try:
                # Get historical prices aligned with purchase date
                prices = fetch_historical_prices(security['ticker'])
                purchase_date = datetime.strptime(security['purchase_date'], "%Y-%m-%d")
                filtered_prices = [price for date, price in prices if date >= purchase_date]

                if len(filtered_prices) < 2:
                    continue

                returns = self._calculate_daily_returns(filtered_prices)

                if len(returns) > 0:
                    weight = security['total_value'] / portfolio_value
                    weights.append(weight)
                    historical_returns.append(returns)
            except Exception as e:
                print(f"Error processing {security['ticker']}: {str(e)}")
                continue

        if not historical_returns:
            return self._get_default_var_metrics(portfolio_value)

        # Align return series lengths
        min_length = min(len(returns) for returns in historical_returns)
        historical_returns = [returns[:min_length] for returns in historical_returns]

        # Convert to numpy array for calculations
        returns_array = np.array(historical_returns)
        weights_array = np.array(weights)

        # Calculate portfolio returns considering correlations
        portfolio_returns = np.sum(returns_array * weights_array[:, np.newaxis], axis=0)

        # Detect market regime
        regime_probs = self._detect_market_regime(portfolio_returns)

        # Calculate VaR metrics with time scaling
        var_metrics = self._calculate_var_metrics(
            portfolio_returns,
            portfolio_value,
            regime_probs
        )

        return var_metrics

    def _detect_market_regime(self, returns: np.ndarray) -> Dict[str, float]:
        """
        Detect market regime using volatility clustering.
        Returns probability of being in normal vs stress regime.
        """
        if len(returns) < 30:  # Need minimum sample size
            return {"normal": 0.8, "stress": 0.2}

        # Calculate rolling volatility
        rolling_vol = self._calculate_rolling_volatility(returns, window=20)

        # Define stress threshold as 1.5 standard deviations above mean
        vol_mean = np.mean(rolling_vol)
        vol_std = np.std(rolling_vol)
        stress_threshold = vol_mean + 1.5 * vol_std

        # Calculate regime probabilities
        stress_days = np.sum(rolling_vol > stress_threshold)
        total_days = len(rolling_vol)

        stress_prob = stress_days / total_days
        normal_prob = 1 - stress_prob

        return {
            "normal": normal_prob,
            "stress": stress_prob
        }

    def _calculate_var_metrics(
            self,
            returns: np.ndarray,
            portfolio_value: float,
            regime_probs: Dict[str, float]
    ) -> Dict:
        """
        Calculate VaR metrics with proper time scaling and regime mixing.
        """
        # Parameters
        var_normal_conf = 0.95
        var_stress_conf = 0.99

        # Calculate regime-specific VaRs
        normal_var = np.percentile(returns, (1 - var_normal_conf) * 100)
        stress_var = np.percentile(returns, (1 - var_stress_conf) * 100)

        # Scale to chosen horizon using square root of time rule
        scaling_factor = np.sqrt(self.VAR_HORIZON)
        normal_var_scaled = normal_var * scaling_factor
        stress_var_scaled = stress_var * scaling_factor

        # Calculate Expected Shortfall (CVaR)
        tail_returns = returns[returns <= normal_var]
        cvar = np.mean(tail_returns) * scaling_factor if len(tail_returns) > 0 else normal_var_scaled

        # Adjust for portfolio value
        return {
            "var_normal": normal_var_scaled * portfolio_value,
            "var_stress": stress_var_scaled * portfolio_value,
            "cvar": cvar * portfolio_value,
            "regime_distribution": regime_probs,
            "confidence_levels": {
                "normal": var_normal_conf,
                "stress": var_stress_conf
            },
            "horizon_days": self.VAR_HORIZON
        }

    def get_var_components(self, securities: List[Dict]) -> List[Dict]:
        """Calculate individual security contributions to portfolio VaR"""
        components = []
        portfolio_value = sum(s['total_value'] for s in securities)

        for security in securities:
            try:
                # Fetch (date, price) pairs
                price_data = fetch_historical_prices(security['ticker'])
                # Calculate returns using the modified method
                returns = self._calculate_daily_returns(price_data)

                if len(returns) > 0:
                    # Calculate VaR for component
                    var_95 = np.percentile(returns, 5)
                    var_contrib = var_95 * security['total_value']
                    weight = security['total_value'] / portfolio_value if portfolio_value else 0
                    volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0

                    components.append({
                        "ticker": security['ticker'],
                        "var_contribution": var_contrib,
                        "weight": weight,
                        "volatility": volatility * 100  # Convert to percentage
                    })
                else:
                    print(f"No valid returns data for {security['ticker']}")

            except Exception as e:
                print(f"Error processing {security['ticker']}: {str(e)}")
                continue

        return components

    def _calculate_marginal_var(
            self,
            security_returns: np.ndarray,
            all_returns: np.ndarray,
            weights: np.ndarray,
            correlations: np.ndarray,
            portfolio_value: float
    ) -> float:
        """
        Calculate marginal VaR contribution for a security,
        considering correlations with other portfolio components.
        """
        # Calculate portfolio returns
        portfolio_returns = np.sum(all_returns * weights[:, np.newaxis], axis=0)

        # Calculate VaR at 95% confidence
        var_95 = np.percentile(portfolio_returns, 5)

        # Calculate component VaR
        beta_i = np.sum(correlations * weights)
        marginal_var = beta_i * var_95 * portfolio_value

        return marginal_var

    @staticmethod
    def _calculate_daily_returns(price_data: List[Tuple[Any, float]]) -> np.ndarray:
        """Calculate logarithmic daily returns from price series"""
        try:
            if not price_data:
                print("No price data provided")
                return np.array([])

            print(f"Processing {len(price_data)} price points")

            # Extract just the prices from the (date, price) tuples
            prices = np.array([price for _, price in price_data], dtype=float)

            if len(prices) < 2:
                print("Insufficient price data for returns calculation")
                return np.array([])

            # Calculate log returns
            returns = np.log(prices[1:] / prices[:-1])
            # Remove infinite values and NaNs
            returns = returns[np.isfinite(returns)]

            print(f"Calculated {len(returns)} valid returns")
            return returns

        except Exception as e:
            print(f"Error calculating returns: {str(e)}")
            print(f"Price data sample: {price_data[:5] if price_data else 'None'}")
            return np.array([])

    @staticmethod
    def _calculate_rolling_volatility(returns: np.ndarray, window: int = 20) -> np.ndarray:
        """Calculate rolling volatility of returns"""
        if len(returns) < window:
            return np.array([])

        rolling_vol = np.array([
            np.std(returns[i:i + window])
            for i in range(len(returns) - window + 1)
        ])

        return rolling_vol

    def _get_default_var_metrics(self, portfolio_value: float) -> Dict:
        """Return default VaR metrics for edge cases"""
        return {
            "var_normal": portfolio_value * 0.05,  # Conservative 5% estimate
            "var_stress": portfolio_value * 0.08,  # More conservative stress estimate
            "cvar": portfolio_value * 0.10,  # Even more conservative tail risk
            "regime_distribution": {"normal": 1, "stress": 0},
            "confidence_levels": {
                "normal": 0.95,
                "stress": 0.99
            },
            "horizon_days": self.VAR_HORIZON
        }


