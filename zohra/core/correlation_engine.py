import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from zohra.brokers.manager import broker_manager as mt5_broker
from zohra.config.settings import ACTIVE_PAIRS

logger = logging.getLogger("zohra.correlation_engine")

class CorrelationEngine:
    """
    Computes Pearson correlation matrix dynamically across active pairs.
    Prevents stacking highly-correlated risk exposures.
    """
    def __init__(self, check_period: int = 100):
        self.check_period = check_period
        self.matrix: pd.DataFrame = pd.DataFrame()
        # Conservative long-run relationships used only while live history is
        # unavailable. Unknown relationships remain neutral rather than being
        # guessed, but well-known pairs must not silently bypass the risk gate.
        self.fallback_matrix = {
            "EURUSD": {"GBPUSD": 0.85, "USDCHF": -0.80, "XAUUSD": 0.40, "USDX": -0.95},
            "GBPUSD": {"EURUSD": 0.85},
            "USDCHF": {"EURUSD": -0.80},
            "XAUUSD": {"XAGUSD": 0.90, "EURUSD": 0.40, "USDJPY": -0.35},
            "XAGUSD": {"XAUUSD": 0.90},
            "USDJPY": {"XAUUSD": -0.35},
            "USDX": {"EURUSD": -0.95},
        }

    def update_correlation_matrix(self):
        """Fetches historical close data for all active pairs and updates the correlation matrix."""
        logger.info("📊 Re-calculating live correlation matrix...")
        data = {}
        for symbol in ACTIVE_PAIRS:
            try:
                # Fetch last 100 H1 bars
                rates = mt5_broker.get_multi_tf(symbol, ["H1"], count=self.check_period)
                df = rates.get("H1")
                if df is not None and not df.empty:
                    data[symbol] = df["close"].values
            except Exception as e:
                logger.warning(f"Could not get close prices for correlation mapping of {symbol}: {e}")

        if len(data) < 2:
            logger.warning("Not enough symbols loaded to calculate live correlation matrix. Using fallback matrix.")
            return

        try:
            # Find the minimum length to align series
            min_len = min(len(v) for v in data.values())
            aligned_data = {k: v[-min_len:] for k, v in data.items()}
            
            df_prices = pd.DataFrame(aligned_data)
            self.matrix = df_prices.corr(method="pearson")
            logger.info("✅ Live correlation matrix updated successfully.")
        except Exception as e:
            logger.error(f"Error compiling correlation matrix: {e}")

    def get_correlation(self, symbol_a: str, symbol_b: str) -> float:
        """Returns correlation coefficient between symbol_a and symbol_b."""
        if symbol_a == symbol_b:
            return 1.0

        if not self.matrix.empty:
            if symbol_a in self.matrix.columns and symbol_b in self.matrix.columns:
                val = self.matrix.loc[symbol_a, symbol_b]
                if not np.isnan(val):
                    return float(val)

        # Fallback to static values
        if symbol_a in self.fallback_matrix and symbol_b in self.fallback_matrix[symbol_a]:
            return self.fallback_matrix[symbol_a][symbol_b]
        if symbol_b in self.fallback_matrix and symbol_a in self.fallback_matrix[symbol_b]:
            return self.fallback_matrix[symbol_b][symbol_a]

        return 0.0

    def evaluate_portfolio_exposure(self, proposed_symbol: str, open_positions: List[Dict]) -> Tuple[float, float, str]:
        """
        Calculates correlation score and portfolio risk score.
        Returns:
            Tuple[float, float, str]: (Correlation Score 0-1, Exposure Score, Decision reason/veto)
        """
        if not open_positions:
            return 0.0, 0.0, "Portfolio empty. Correlation risk is zero."

        correlations = []
        high_corr_symbols = []
        from zohra.config.settings import METAL_SYMBOLS
        for pos in open_positions:
            symbol = pos["symbol"]
            # Exempt metal-to-metal correlation (naturally correlated, we want both)
            if proposed_symbol in METAL_SYMBOLS and symbol in METAL_SYMBOLS:
                continue
            corr_val = self.get_correlation(proposed_symbol, symbol)
            correlations.append(abs(corr_val))
            if abs(corr_val) >= 0.75:
                high_corr_symbols.append(f"{symbol} (r={corr_val:+.2f})")

        max_correlation = max(correlations) if correlations else 0.0
        avg_correlation = sum(correlations) / len(correlations) if correlations else 0.0
        
        exposure_score = max_correlation * len(open_positions)
        
        reason = f"Max correlation with open trades is {max_correlation:.2f}. Average is {avg_correlation:.2f}."
        if high_corr_symbols:
            reason += f" VETO Warning: High correlation with {', '.join(high_corr_symbols)}"

        return max_correlation, exposure_score, reason

correlation_engine = CorrelationEngine()
