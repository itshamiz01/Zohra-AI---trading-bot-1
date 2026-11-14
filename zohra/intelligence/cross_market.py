"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — CROSS-MARKET INTELLIGENCE ENGINE                   ║
║     Inter-Market Correlation, Capital Rotation, Global Sentiment    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

import numpy as np

from zohra.intelligence.models import CrossMarketIntel
from zohra.config.settings import INTELLIGENCE_CROSS_MARKET_ASSETS

logger = logging.getLogger("zohra.intelligence.cross_market")

# Known inter-market relationships for static fallback
STATIC_CORRELATIONS = {
    "XAUUSD": {"XAGUSD": 0.90, "EURUSD": 0.40, "USDJPY": -0.35, "BTCUSDT": 0.25, "US500": -0.15, "USDX": -0.80},
    "XAGUSD": {"XAUUSD": 0.90, "EURUSD": 0.35, "BTCUSDT": 0.20},
    "EURUSD": {"GBPUSD": 0.85, "USDCHF": -0.80, "XAUUSD": 0.40, "USDX": -0.95},
    "USDJPY": {"XAUUSD": -0.35, "US500": 0.45, "USDX": 0.50},
    "BTCUSDT": {"ETHUSDT": 0.92, "US500": 0.60, "NAS100": 0.65, "XAUUSD": 0.25, "USDX": -0.40},
    "ETHUSDT": {"BTCUSDT": 0.92, "US500": 0.55, "NAS100": 0.60},
    "US500": {"NAS100": 0.95, "BTCUSDT": 0.60, "USDJPY": 0.45, "XAUUSD": -0.15},
    "NAS100": {"US500": 0.95, "BTCUSDT": 0.65, "ETHUSDT": 0.60},
    "USDX": {"EURUSD": -0.95, "XAUUSD": -0.80, "BTCUSDT": -0.40},
}


class CrossMarketEngine:
    """
    Analyzes relationships between global asset classes to detect
    capital rotation, risk-on/risk-off shifts, and institutional flows.
    """

    def __init__(self):
        self._tracked_assets = INTELLIGENCE_CROSS_MARKET_ASSETS
        self._latest_intel: Optional[CrossMarketIntel] = None

    def analyze(self) -> CrossMarketIntel:
        """Run cross-market analysis using live + static data."""
        corr_matrix = self._build_correlation_matrix()
        rotation = self._detect_capital_rotation()
        sentiment = self._compute_global_sentiment()
        flow = self._estimate_institutional_flow()
        dxy = self._get_dxy_trend()
        vix = self._get_vix_level()
        bond = self._get_bond_yield_trend()

        intel = CrossMarketIntel(
            correlation_matrix=corr_matrix,
            capital_rotation=rotation,
            risk_sentiment=sentiment["sentiment"],
            global_sentiment_score=sentiment["score"],
            institutional_flow=flow,
            dxy_trend=dxy,
            vix_level=vix,
            bond_yield_trend=bond,
        )
        self._latest_intel = intel
        return intel

    # ─── Correlation Matrix ───────────────────────────────────

    def _build_correlation_matrix(self) -> Dict[str, Dict[str, float]]:
        """Build correlation matrix from live data with static fallback."""
        # Try live data first
        live_data = self._fetch_live_prices()
        if live_data and len(live_data) >= 3:
            return self._compute_live_correlations(live_data)
        return self._static_correlation_matrix()

    @staticmethod
    def _static_correlation_matrix() -> Dict[str, Dict[str, float]]:
        """Return a complete symmetric fallback matrix for offline risk analysis."""
        matrix: Dict[str, Dict[str, float]] = {}
        for source, relationships in STATIC_CORRELATIONS.items():
            matrix.setdefault(source, {})[source] = 1.0
            for target, correlation in relationships.items():
                matrix[source][target] = correlation
                matrix.setdefault(target, {})[source] = correlation
                matrix[target].setdefault(target, 1.0)
        return matrix

    def _compute_live_correlations(self, price_data: Dict[str, np.ndarray]) -> Dict[str, Dict[str, float]]:
        """Compute Pearson correlations from live close prices."""
        symbols = list(price_data.keys())
        min_len = min(len(v) for v in price_data.values())
        aligned = {k: v[-min_len:] for k, v in price_data.items()}

        # Compute returns
        returns = {}
        for sym, prices in aligned.items():
            if len(prices) > 1:
                pct = np.diff(prices) / prices[:-1]
                returns[sym] = pct

        matrix: Dict[str, Dict[str, float]] = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                elif s1 in returns and s2 in returns:
                    ml = min(len(returns[s1]), len(returns[s2]))
                    if ml > 5:
                        corr = float(np.corrcoef(returns[s1][-ml:], returns[s2][-ml:])[0, 1])
                        matrix[s1][s2] = round(corr, 3)
        return matrix

    # ─── Capital Rotation ─────────────────────────────────────

    def _detect_capital_rotation(self) -> Dict[str, str]:
        """Detect inflow/outflow patterns across asset classes."""
        rotation = {}
        try:
            bm = self._get_broker_manager()
            if bm is None:
                return rotation

            for asset in ["XAUUSD", "BTCUSDT", "US500"]:
                try:
                    df = bm.get_ohlcv(asset, "D1", count=10)
                    if df is not None and len(df) >= 5:
                        close = df["close"].values
                        trend = float(close[-1] - close[-5]) / max(abs(close[-5]), 1e-9) * 100
                        rotation[asset] = "inflow" if trend > 1 else "outflow" if trend < -1 else "neutral"
                except Exception:
                    pass
        except Exception:
            pass
        return rotation

    # ─── Global Sentiment ─────────────────────────────────────

    def _compute_global_sentiment(self) -> Dict[str, Any]:
        """Compute a global sentiment score (0=extreme fear, 100=extreme greed)."""
        score = 50.0
        try:
            bm = self._get_broker_manager()
            if bm:
                # Gold rising = fear (score drops)
                gold = bm.get_ohlcv("XAUUSD", "D1", count=5)
                if gold is not None and len(gold) >= 3:
                    gold_trend = float(gold["close"].values[-1] - gold["close"].values[-3])
                    if gold_trend > 0:
                        score -= 10
                    else:
                        score += 5

        except Exception:
            pass

        score = max(0, min(100, score))
        sentiment = "risk_on" if score > 60 else "risk_off" if score < 40 else "neutral"
        return {"score": round(score, 1), "sentiment": sentiment}

    # ─── Institutional Flow ───────────────────────────────────

    def _estimate_institutional_flow(self) -> Dict[str, str]:
        """Estimate institutional flow direction per asset class."""
        flow: Dict[str, str] = {}
        try:
            bm = self._get_broker_manager()
            if bm is None:
                return flow

            for asset in self._tracked_assets[:5]:  # Top 5
                try:
                    df = bm.get_ohlcv(asset, "H4", count=20)
                    if df is not None and len(df) >= 10:
                        vol = df["tick_volume"].values if "tick_volume" in df.columns else np.ones(len(df))
                        close = df["close"].values
                        recent_vol = float(np.mean(vol[-5:]))
                        avg_vol = float(np.mean(vol[-20:]))
                        trend = float(close[-1] - close[-5])

                        if recent_vol > avg_vol * 1.3 and trend > 0:
                            flow[asset] = "institutional_buying"
                        elif recent_vol > avg_vol * 1.3 and trend < 0:
                            flow[asset] = "institutional_selling"
                        else:
                            flow[asset] = "neutral"
                except Exception:
                    pass
        except Exception:
            pass
        return flow

    # ─── Market Indicators ────────────────────────────────────

    def _get_dxy_trend(self) -> str:
        try:
            bm = self._get_broker_manager()
            if bm:
                df = bm.get_ohlcv("USDX", "D1", count=5)
                if df is not None and len(df) >= 3:
                    trend = float(df["close"].values[-1] - df["close"].values[-3])
                    return "BULLISH" if trend > 0 else "BEARISH" if trend < 0 else "NEUTRAL"
        except Exception:
            pass
        return "NEUTRAL"

    @staticmethod
    def _get_vix_level() -> float:
        """VIX placeholder — requires data feed."""
        return 18.5  # Default moderate level

    @staticmethod
    def _get_bond_yield_trend() -> str:
        """Bond yield trend placeholder."""
        return "NEUTRAL"

    # ─── Data Access ──────────────────────────────────────────

    def _fetch_live_prices(self) -> Dict[str, np.ndarray]:
        """Fetch live close prices for tracked assets."""
        data = {}
        try:
            bm = self._get_broker_manager()
            if bm is None:
                return data
            for asset in self._tracked_assets:
                try:
                    df = bm.get_ohlcv(asset, "H1", count=100)
                    if df is not None and len(df) >= 20:
                        data[asset] = df["close"].values
                except Exception:
                    pass
        except Exception:
            pass
        return data

    @staticmethod
    def _get_broker_manager():
        try:
            from zohra.brokers.manager import broker_manager
            return broker_manager
        except ImportError:
            return None

    # ─── Convenience ──────────────────────────────────────────

    def get_intel(self) -> Dict[str, Any]:
        """Return latest cross-market intelligence as dict."""
        intel = self._latest_intel or self.analyze()
        return intel.to_dict()

    def compare_assets(self, asset_a: str, asset_b: str) -> Dict[str, Any]:
        """Compare two specific assets."""
        corr = STATIC_CORRELATIONS.get(asset_a, {}).get(asset_b, 0.0)
        if corr == 0.0:
            corr = STATIC_CORRELATIONS.get(asset_b, {}).get(asset_a, 0.0)

        relationship = "positively correlated" if corr > 0.3 else "inversely correlated" if corr < -0.3 else "uncorrelated"

        return {
            "asset_a": asset_a,
            "asset_b": asset_b,
            "correlation": corr,
            "relationship": relationship,
            "summary": f"{asset_a} and {asset_b} are {relationship} (r={corr:.2f}).",
        }


# Singleton
cross_market_engine = CrossMarketEngine()
