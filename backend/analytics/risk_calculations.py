from datetime import datetime, timedelta, date

from flask import current_app
from scipy import stats
import numpy as np
import traceback
from typing import List, Dict, Optional, Tuple, Any, Union
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import threading

from .market_data import fetch_historical_prices
from ..models import SecurityHistoricalData


# I don't think i want to implement this yet. keeping it here as a reminder
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


class RiskAnalytics:
    def __init__(self):
        self.market_data = None
        self.RISK_FREE_RATE = 0.05  # 5% annual rate - should be fetched from market data
        self.VAR_HORIZON = 10  # 10-day VaR
        self.TRADING_DAYS = 252  # Number of trading days in a year

        self._cache_lock = threading.Lock()
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.app = current_app._get_current_object()

        # for the beta calculations
        self.benchmark_symbols = {
            'US_BROAD': '^GSPC',  # S&P 500
            'US_TECH': '^NDX',  # NASDAQ-100
            'US_SMALL': '^RUT',  # Russell 2000
            'GLOBAL': 'ACWI',  # MSCI All Country World Index
            'EUROPE': '^STOXX',  # STOXX Europe 600
            'EMERGING': 'EEM'  # iShares MSCI Emerging Markets ETF
        }

    @lru_cache(maxsize=100)
    def _get_historical_data(self, ticker: str, start_date: datetime.date,
                             end_date: datetime.date) -> Optional[List]:
        """Cached historical data retrieval with application context"""
        with self.app.app_context():
            hist_data = SecurityHistoricalData.query.filter(
                SecurityHistoricalData.ticker == ticker,
                SecurityHistoricalData.date >= start_date,
                SecurityHistoricalData.date <= end_date
            ).order_by(SecurityHistoricalData.date).all()

            return hist_data if hist_data else None

    def _process_security_returns(self, security: Dict, portfolio_value: float,
                                  start_date: datetime.date,
                                  end_date: datetime.date) -> Tuple[Optional[np.ndarray], Optional[float]]:
        """Process returns for a single security"""
        try:
            print(f"\nProcessing security: {security['ticker']}")

            hist_data = self._get_historical_data(security['ticker'], start_date, end_date)

            print(f"Found {len(hist_data) if hist_data else 0} historical records")

            if hist_data:
                # Print first few records for debugging
                for record in hist_data[:3]:
                    print(f"Record: {record.date}: {record.adjusted_close}")

                prices = np.array([float(data.adjusted_close) for data in hist_data])
                returns = np.diff(np.log(prices))

                if len(returns) > 0:
                    weight = security['total_value'] / portfolio_value
                    print(f"Added returns for {security['ticker']}, weight: {weight:.4f}")
                    print(f"First few returns: {returns[:3]}")
                    return returns, weight

            return None, None

        except Exception as e:
            print(f"Error processing security {security['ticker']}: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return None, None

    def calculate_portfolio_risk(self, portfolio_id: int, securities: List[Dict]) -> Dict:
        """Calculate comprehensive portfolio risk metrics"""
        try:
            portfolio_value = sum(s['total_value'] for s in securities)

            # Launch calculations in parallel
            with ThreadPoolExecutor(max_workers=4) as executor:
                var_future = executor.submit(self.calculate_dynamic_var, securities)
                beta_future = executor.submit(self.calculate_portfolio_beta, securities)
                components_future = executor.submit(self.get_var_components, securities)
                credit_future = executor.submit(self.calculate_credit_risk, securities)

                # Get results with timeout
                var_metrics = var_future.result(timeout=2)
                beta = beta_future.result(timeout=2)
                var_components = components_future.result(timeout=2)
                credit_risk = credit_future.result(timeout=1)

            return {
                "total_value": portfolio_value,
                "beta": beta,
                "var_metrics": var_metrics,
                "var_components": var_components,
                "credit_risk": credit_risk
            }

        except Exception as e:
            print(f"Error in parallel calculation: {str(e)}")
            # Return default values if calculation fails
            return self._get_default_risk_metrics(portfolio_value)

    def _get_default_risk_metrics(self, portfolio_value: float) -> Dict:
        """Return default risk metrics if calculation fails"""
        return {
            "total_value": portfolio_value,
            "beta": self._get_default_beta_metrics(),
            "var_metrics": self._get_default_var_metrics(portfolio_value),
            "var_components": [],
            "credit_risk": {"cs01": portfolio_value * 0.0001}
        }

    def calculate_portfolio_beta(self, securities_data: List[Dict], lookback_days: int = 252) -> Dict:
        """Calculate comprehensive beta metrics for the portfolio."""
        try:
            print(f"\n==== DEBUG: calculate_portfolio_beta ====")
            print(f"Number of securities: {len(securities_data)}")
            print(f"Securities data: {securities_data[:2]}")  # Print first 2 securities
_portfolio_beta ====")
        print(f"Number of securities: {len(securities_data)}")
        """Calculate comprehensive beta metrics for the portfolio."""
        try:
            print(f"Calculating beta for {len(securities_data)} securities")

            # Get dates for lookback period
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=lookback_days)
            print(f"Date range: {start_date} to {end_date}")

            # Calculate portfolio returns
            portfolio_returns = self._get_portfolio_returns(securities_data, start_date, end_date)
            print(f"Portfolio returns: {portfolio_returns[:5] if portfolio_returns is not None else None}")
            if portfolio_returns is None:
                print("Failed to get portfolio returns, returning default metrics")
                return self._get_default_beta_metrics()

            # Get benchmark returns
            with self.app.app_context():
                benchmark_data = self._get_historical_data("SPY", start_date, end_date)
                print(f"Benchmark data: {benchmark_data[:2] if benchmark_data else None}")
                if not benchmark_data:
                    print("Failed to get benchmark returns")
                    return self._get_default_beta_metrics()

                benchmark_prices = np.array([float(data.adjusted_close) for data in benchmark_data])
                benchmark_returns = np.diff(np.log(benchmark_prices))
                print(f"Benchmark returns: {benchmark_returns[:5] if len(benchmark_returns) > 0 else []}")

            # Calculate beta metrics
            standard_beta = self._calculate_standard_beta(portfolio_returns, benchmark_returns)
            print(f"Standard beta: {standard_beta}")
            print(f"DEBUG: standard_beta = {standard_beta}")
            rolling_betas = self._calculate_rolling_beta(portfolio_returns, benchmark_returns)
            downside_beta = self._calculate_downside_beta(portfolio_returns, benchmark_returns)

            # Calculate confidence metrics
            r_squared, std_error = self._calculate_beta_statistics(portfolio_returns, benchmark_returns)

            print(f"DEBUG: Returning beta dictionary with beta = {standard_beta}")
            return {
                'beta': standard_beta,
                'downside_beta': downside_beta,
                'rolling_betas': rolling_betas.tolist(),
                'r_squared': r_squared,
                'standard_error': std_error,
                'confidence': {
                    'high': standard_beta + (1.96 * std_error),
                    'low': standard_beta - (1.96 * std_error)
                }
            }

        except Exception as e:
            print(f"Error calculating beta: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return self._get_default_beta_metrics()

    def _get_benchmark_returns(self, start_date: datetime.date, end_date: datetime.date) -> np.ndarray:
        """Get benchmark returns from historical data table."""
        try:
            print(f"Getting benchmark returns from {start_date} to {end_date}")

            # Ensure we're using the correct benchmark ticker (SPY instead of ^GSPC)
            benchmark_ticker = 'SPY'  # Use SPY ETF instead of ^GSPC
            print(f"Using benchmark ticker: {benchmark_ticker}")

            # Query historical data for benchmark
            benchmark_data = SecurityHistoricalData.query.filter(
                SecurityHistoricalData.ticker == benchmark_ticker,
                SecurityHistoricalData.date >= start_date,
                SecurityHistoricalData.date <= end_date
            ).order_by(SecurityHistoricalData.date).all()

            print(f"Found {len(benchmark_data) if benchmark_data else 0} benchmark data points")

            if not benchmark_data:
                print("No benchmark data found!")
                print("Available tickers:", SecurityHistoricalData.query.with_entities(
                    SecurityHistoricalData.ticker).distinct().all())
                return None

            # Print first few records for debugging
            for record in benchmark_data[:5]:
                print(f"Benchmark record: {record.date}: {record.adjusted_close}")

            # Calculate daily returns using adjusted close prices
            prices = np.array([float(data.adjusted_close) for data in benchmark_data])
            returns = np.diff(np.log(prices))

            print(f"Calculated {len(returns)} benchmark returns")
            print(f"First few returns: {returns[:5]}")
            print(f"Returns statistics: mean={np.mean(returns):.6f}, std={np.std(returns):.6f}")

            return returns

        except Exception as e:
            print(f"Error getting benchmark returns: {str(e)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return None

    def _calculate_standard_beta(
            self,
            portfolio_returns: np.ndarray,
            benchmark_returns: np.ndarray
    ) -> float:
        """Calculate standard beta using regression."""
        if len(portfolio_returns) != len(benchmark_returns):
            # Align the lengths by taking the minimum length
            min_length = min(len(portfolio_returns), len(benchmark_returns))
            portfolio_returns = portfolio_returns[:min_length]
            benchmark_returns = benchmark_returns[:min_length]
            
            # If we don't have enough data, return a default
            if min_length < 20:  # Need at least 20 data points for a meaningful beta
                return 1.0

        # Check for zero variance in benchmark returns
        if np.var(benchmark_returns) == 0:
            return 1.0  # Default if benchmark returns are constant

        try:
            slope, _, r_value, _, _ = stats.linregress(benchmark_returns, portfolio_returns)
            
            # Check for NaN or infinite values
            if np.isnan(slope) or np.isinf(slope):
                return 1.0  # Default if regression fails
                
            return slope
        except Exception as e:
            print(f"Error in beta calculation: {str(e)}")
            return 1.0  # Default if regression fails
    def _get_portfolio_returns(self, securities_data: List[Dict], start_date: datetime.date,
                             end_date: datetime.date) -> Optional[np.ndarray]:
        """Calculate portfolio returns using historical data."""
        try:
            portfolio_value = sum(s['total_value'] for s in securities_data)
            print(f"\nCalculating portfolio returns:")
            print(f"Date range: {start_date} to {end_date}")
            print(f"Portfolio value: {portfolio_value}")
            print(f"Number of securities: {len(securities_data)}")

            all_returns = []
            weights = []

            # Process each security within app context
            with self.app.app_context():
                for security in securities_data:
                    returns, weight = self._process_security_returns(
                        security, portfolio_value, start_date, end_date
                    )
                    if returns is not None and weight is not None:
                        all_returns.append(returns)
                        weights.append(weight)

            if not all_returns:
                print("No valid returns calculated")
                return None

            # Align return series lengths
            min_length = min(len(returns) for returns in all_returns)
            print(f"\nAligning return series to length: {min_length}")
            all_returns = [returns[:min_length] for returns in all_returns]

            # Calculate weighted portfolio returns
            portfolio_returns = np.sum(
                [returns * weight for returns, weight in zip(all_returns, weights)],
                axis=0
            )

            print("\nPortfolio returns statistics:")
            print(f"Mean: {np.mean(portfolio_returns):.6f}")
            print(f"Std: {np.std(portfolio_returns):.6f}")
            print(f"Length: {len(portfolio_returns)}")

            return portfolio_returns

        except Exception as e:
            print(f"Error calculating portfolio returns: {str(e)}")
            print(f"Traceback: {traceback.format_exc()}")
            return None

    def _calculate_rolling_beta(
            self,
            portfolio_returns: np.ndarray,
            benchmark_returns: np.ndarray,
            window: int = 60
    ) -> np.ndarray:
        """Calculate rolling beta over specified window."""
        rolling_betas = []
        for i in range(window, len(portfolio_returns) + 1):
            window_portfolio = portfolio_returns[i - window:i]
            window_benchmark = benchmark_returns[i - window:i]
            beta = self._calculate_standard_beta(window_portfolio, window_benchmark)
            rolling_betas.append(beta)

        return np.array(rolling_betas)

    def _calculate_downside_beta(
            self,
            portfolio_returns: np.ndarray,
            benchmark_returns: np.ndarray
    ) -> float:
        """Calculate downside beta (beta during negative benchmark returns)."""
        mask = benchmark_returns < 0
        if not any(mask):
            return self._calculate_standard_beta(portfolio_returns, benchmark_returns)

        down_portfolio = portfolio_returns[mask]
        down_benchmark = benchmark_returns[mask]

        if len(down_portfolio) < 2:
            return 1.0

        slope, _, _, _, _ = stats.linregress(down_benchmark, down_portfolio)
        return slope

    def _calculate_beta_statistics(
            self,
            portfolio_returns: np.ndarray,
            benchmark_returns: np.ndarray
    ) -> Tuple[float, float]:
        """Calculate beta statistical metrics."""
        if len(portfolio_returns) != len(benchmark_returns):
            return 0.0, 0.0

        slope, _, r_value, _, std_err = stats.linregress(
            benchmark_returns,
            portfolio_returns
        )

        r_squared = r_value ** 2
        return r_squared, std_err

    def _get_default_beta_metrics(self) -> Dict:
        """Return default beta metrics when calculation fails."""
        return {
            'beta': 1.0,
            'downside_beta': 1.0,
            'rolling_betas': [1.0] * 60,
            'r_squared': 0.0,
            'standard_error': 0.0,
            'confidence': {
                'high': 1.2,
                'low': 0.8
            },
            'analysis': {
                'trend': 'stable',
                'stability': 'high'
            }
        }

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
                purchase_date = datetime.strptime(security['purchase_date'], "%Y-%m-%d").date()
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
    def _calculate_daily_returns(price_data: Union[List[Tuple[Any, float]], List[float], np.ndarray]) -> np.ndarray:
        try:
            if not price_data:
                print("No price data provided")
                return np.array([])

            print(f"Processing {len(price_data)} price points")

            # Handle different input formats
            if isinstance(price_data, np.ndarray):
                prices = price_data
            elif isinstance(price_data[0], (tuple, list)):
                # Extract just the prices from the (date, price) tuples
                prices = np.array([price for _, price in price_data], dtype=float)
            else:
                # Direct list of prices
                prices = np.array(price_data, dtype=float)

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
            print(f"Price data type: {type(price_data)}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
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