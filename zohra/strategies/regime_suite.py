"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — 15-STRATEGY CONFLUENCE SUITE ROUTER             ║
║                  Institutional Gold (XAUUSD) Scalper                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd

from zohra.core.enums import StrategyName, MarketRegime
from zohra.core.market_regime import market_regime_engine
from zohra.core.confluence_engine import confluence_engine, ConfluenceDecision

logger = logging.getLogger("zohra.strategies.regime_suite")


class RegimeStrategySuite:
    """
    Unified 15-Strategy Regime-Adaptive Confluence Trading Engine for Gold (XAUUSD).
    Coordinates Market Regime Detection, Strategy Eligibility Routing,
    15-Strategy Signal Generation, Group Independence Validation, and Diagnostic Logging.
    """

    def __init__(self):
        self.confluence_engine = confluence_engine

    def evaluate(self, df_m5: pd.DataFrame, symbol: str = "XAUUSD",
                 ask: float = 0.0, bid: float = 0.0,
                 htf_dfs: Optional[Dict[str, pd.DataFrame]] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Full evaluation cycle:
        1. Central Hard Symbol Guard (XAUUSD Only)
        2. Market Regime Classification (9 Regimes)
        3. 15-Strategy Eligibility Filter & Signal Generation
        4. Directional Confluence & Group Independence Arbitration
        5. Formatted Diagnostic Summary String
        """
        # Central Hard Symbol Guard
        from zohra.core.symbol_resolver import CANONICAL_GOLD, symbol_resolver
        clean_symbol = str(symbol or "").strip().upper()
        if (
            not symbol_resolver.is_symbol_allowed(symbol)
            or not (clean_symbol.startswith(CANONICAL_GOLD) or clean_symbol.startswith("GOLD"))
        ):
            return None, f"BLOCKED: Trading disabled for {symbol}. Gold only mode is active."

        if df_m5 is None or len(df_m5) < 30:
            return None, f"Insufficient data for {symbol} ({len(df_m5) if df_m5 is not None else 0} bars)."

        # 1. Market Regime Classification
        df_htf = None
        if htf_dfs:
            df_htf = htf_dfs.get("M15") if htf_dfs.get("M15") is not None else htf_dfs.get("H1")
        regime_report = market_regime_engine.classify_regime(df_m5, df_htf)

        # 2. Spread Calculation
        spread_pips = round((ask - bid) * 10.0, 2) if (ask and bid and ask > bid) else 2.0

        # 3. 15-Strategy Confluence Arbitration
        decision, _ = self.confluence_engine.evaluate_all(
            df_entry=df_m5,
            df_htf=df_htf,
            regime_report=regime_report,
            current_spread_pips=spread_pips
        )

        winning_signal = None
        if decision.action == "TRADE" and decision.winning_signal:
            sig = decision.winning_signal
            winning_signal = {
                "symbol": symbol,
                "direction": sig.direction,
                "strategy": sig.strategy_name,
                "strategy_group": sig.strategy_group,
                "entry_price": sig.entry_price,
                "stop_loss": sig.stop_loss,
                "take_profit": sig.take_profit,
                "risk_reward": sig.risk_reward,
                "stop_distance_pips": sig.stop_distance_pips,
                "confidence": decision.final_score,
                "grade": decision.grade,
                "raw_confirmations": decision.raw_confirmations,
                "independent_groups": decision.independent_groups,
                "supporting_strategies": decision.supporting_strategies,
                "reasons": sig.reasons,
                "fingerprint": decision.fingerprint
            }

        return winning_signal, decision.diagnostic_box


# Singleton instance
regime_strategy_suite = RegimeStrategySuite()
