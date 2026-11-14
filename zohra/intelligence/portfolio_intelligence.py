"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — MULTI-ASSET PORTFOLIO INTELLIGENCE                 ║
║     Enterprise Portfolio Management Across All Trading Engines       ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np

from zohra.intelligence.models import (
    PortfolioSnapshot, AllocationBreakdown, RiskMetrics,
)

logger = logging.getLogger("zohra.intelligence.portfolio")


class PortfolioIntelligence:
    """
    Aggregates positions from ALL brokers (MT5, Dhan, CoinDCX) and computes
    institutional-grade portfolio analytics: Sharpe, Sortino, Calmar, VaR,
    CVaR, diversification, health score, exposure analysis, and rebalancing.
    """

    def __init__(self):
        self._snapshot: Optional[PortfolioSnapshot] = None
        self._return_history: List[float] = []
        self._stress_scenarios = {
            "2008_crisis":    {"forex": -0.12, "metals": 0.25, "indices": -0.45, "crypto": -0.60},
            "covid_crash":    {"forex": -0.05, "metals": 0.10, "indices": -0.35, "crypto": -0.50},
            "crypto_winter":  {"forex": 0.0,   "metals": 0.05, "indices": -0.05, "crypto": -0.75},
            "rate_hike_shock":{"forex": -0.08, "metals": -0.15, "indices": -0.20, "crypto": -0.30},
            "geopolitical":   {"forex": -0.06, "metals": 0.20, "indices": -0.15, "crypto": -0.25},
        }

    # ─── Core Portfolio Snapshot ───────────────────────────────

    def build_snapshot(self) -> PortfolioSnapshot:
        """Build a complete portfolio snapshot across all brokers."""
        try:
            from zohra.brokers.manager import broker_manager
        except ImportError:
            broker_manager = None

        positions = []
        total_equity = 0.0
        total_margin = 0.0
        free_margin = 0.0

        # Aggregate across all connected brokers
        broker_names = ["mt5", "dhan", "coindcx"]
        registered_brokers = broker_manager.get_registered_brokers() if broker_manager else []
        for broker_name in broker_names:
            if broker_name not in registered_brokers:
                continue
            try:
                if broker_manager is None:
                    continue
                acct = broker_manager.get_account_info(broker=broker_name)
                if acct and acct.get("equity", 0) > 0:
                    total_equity += acct.get("equity", 0)
                    total_margin += acct.get("margin", 0)
                    free_margin += acct.get("free_margin", 0)

                broker_positions = broker_manager.get_open_positions(broker=broker_name)
                if broker_positions:
                    for pos in broker_positions:
                        pos["_broker"] = broker_name
                    positions.extend(broker_positions)
            except Exception as e:
                logger.debug(f"Could not aggregate from {broker_name}: {e}")

        # Build allocation breakdown
        allocation = self._compute_allocations(positions, total_equity)

        # Build risk metrics
        risk = self._compute_risk_metrics(positions, total_equity)

        # Correlation matrix
        corr_matrix = self._compute_position_correlations(positions)

        # Health score
        health = self._compute_health_score(allocation, risk, len(positions))

        # Recommendations
        recommendations = self._generate_recommendations(allocation, risk, health)

        snapshot = PortfolioSnapshot(
            total_equity=total_equity,
            total_margin_used=total_margin,
            free_margin=free_margin,
            open_positions=len(positions),
            allocation=allocation,
            risk_metrics=risk,
            health_score=health,
            correlation_matrix=corr_matrix,
            recommendations=recommendations,
        )
        self._snapshot = snapshot
        return snapshot

    # ─── Allocation Analysis ──────────────────────────────────

    def _compute_allocations(self, positions: List[Dict], equity: float) -> AllocationBreakdown:
        """Compute allocation breakdown by market, sector, currency."""
        alloc = AllocationBreakdown()
        if equity <= 0 or not positions:
            alloc.cash_pct = 100.0
            return alloc

        market_exposure = {"forex": 0.0, "indian": 0.0, "crypto": 0.0}
        sector_exposure: Dict[str, float] = {}
        currency_exposure: Dict[str, float] = {}

        for pos in positions:
            profit = abs(pos.get("profit", 0))
            volume = pos.get("volume", 0)
            notional = volume * pos.get("price", pos.get("price_open", 0))
            exposure = max(profit, notional * 0.01)  # Approximate exposure

            broker = pos.get("_broker", "mt5")
            symbol = pos.get("symbol", "")

            if broker == "coindcx" or "USDT" in symbol:
                market_exposure["crypto"] += exposure
            elif broker == "dhan" or symbol in ("NIFTY", "BANKNIFTY"):
                market_exposure["indian"] += exposure
            else:
                market_exposure["forex"] += exposure

            sector = pos.get("sector", "unknown")
            sector_exposure[sector] = sector_exposure.get(sector, 0) + exposure

            # Currency extraction from symbol
            if len(symbol) >= 6:
                base = symbol[:3]
                quote = symbol[3:6]
                currency_exposure[base] = currency_exposure.get(base, 0) + exposure
                currency_exposure[quote] = currency_exposure.get(quote, 0) + exposure

        total_exposure = sum(market_exposure.values())
        if total_exposure > 0:
            alloc.forex_pct = round(market_exposure["forex"] / total_exposure * 100, 2)
            alloc.indian_market_pct = round(market_exposure["indian"] / total_exposure * 100, 2)
            alloc.crypto_pct = round(market_exposure["crypto"] / total_exposure * 100, 2)
        alloc.cash_pct = round(max(0, 100 - alloc.forex_pct - alloc.indian_market_pct - alloc.crypto_pct), 2)

        if total_exposure > 0:
            alloc.by_sector = {k: round(v / total_exposure * 100, 2) for k, v in sector_exposure.items()}
            alloc.by_currency = {k: round(v / total_exposure * 100, 2) for k, v in currency_exposure.items()}

        return alloc

    # ─── Risk Metrics ─────────────────────────────────────────

    def _compute_risk_metrics(self, positions: List[Dict], equity: float) -> RiskMetrics:
        """Compute Sharpe, Sortino, Calmar, VaR, CVaR, drawdown."""
        risk = RiskMetrics()
        if not self._return_history or equity <= 0:
            return risk

        returns = np.array(self._return_history[-252:])  # Last year of daily returns
        if len(returns) < 5:
            return risk

        mean_return = float(np.mean(returns))
        std_return = float(np.std(returns))
        downside = returns[returns < 0]
        downside_std = float(np.std(downside)) if len(downside) > 0 else 1e-9

        # Sharpe (annualized, risk-free = 0)
        risk.sharpe_ratio = round((mean_return / max(std_return, 1e-9)) * math.sqrt(252), 2)

        # Sortino
        risk.sortino_ratio = round((mean_return / max(downside_std, 1e-9)) * math.sqrt(252), 2)

        # VaR (95% Historical)
        sorted_returns = np.sort(returns)
        var_index = int(0.05 * len(sorted_returns))
        risk.var_95 = round(float(sorted_returns[var_index]) * equity, 2) if var_index < len(sorted_returns) else 0.0

        # CVaR (average of returns below VaR)
        tail = sorted_returns[:max(var_index, 1)]
        risk.cvar_95 = round(float(np.mean(tail)) * equity, 2)

        # Max Drawdown
        cumulative = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - peak) / peak
        risk.max_drawdown_pct = round(float(np.min(drawdowns)) * 100, 2)
        risk.current_drawdown_pct = round(float(drawdowns[-1]) * 100, 2) if len(drawdowns) > 0 else 0.0

        # Calmar
        if risk.max_drawdown_pct != 0:
            annualized_return = mean_return * 252
            risk.calmar_ratio = round(annualized_return / abs(risk.max_drawdown_pct / 100), 2)

        risk.expected_return = round(mean_return * 252 * 100, 2)

        # Capital Efficiency: return / margin used
        total_margin = sum(pos.get("margin", 0) for pos in positions) if positions else 0
        if total_margin > 0:
            risk.capital_efficiency = round(mean_return * 252 * equity / total_margin, 2)

        # Diversification score (based on number of distinct markets/sectors)
        markets = set()
        for pos in positions:
            markets.add(pos.get("_broker", "unknown"))
            markets.add(pos.get("sector", "unknown"))
        risk.diversification_score = min(100, len(markets) * 15)

        return risk

    def record_daily_return(self, pct_return: float):
        """Record a daily portfolio return for rolling analytics."""
        self._return_history.append(pct_return)
        if len(self._return_history) > 504:  # Keep ~2 years
            self._return_history = self._return_history[-504:]

    # ─── Correlation ──────────────────────────────────────────

    def _compute_position_correlations(self, positions: List[Dict]) -> Dict[str, Dict[str, float]]:
        """Static fallback correlation matrix for open position symbols."""
        static_corr = {
            "EURUSD": {"GBPUSD": 0.85, "USDCHF": -0.80, "USDJPY": -0.20, "XAUUSD": 0.40},
            "GBPUSD": {"EURUSD": 0.85, "USDCHF": -0.75, "XAUUSD": 0.35},
            "XAUUSD": {"XAGUSD": 0.90, "EURUSD": 0.40, "BTCUSDT": 0.25},
            "BTCUSDT": {"ETHUSDT": 0.92, "XAUUSD": 0.25, "US500": 0.60},
            "ETHUSDT": {"BTCUSDT": 0.92, "US500": 0.55},
        }
        symbols = list(set(p.get("symbol", "") for p in positions))
        matrix: Dict[str, Dict[str, float]] = {}
        for s in symbols:
            matrix[s] = static_corr.get(s, {})
        return matrix

    # ─── Health Score ─────────────────────────────────────────

    def _compute_health_score(self, alloc: AllocationBreakdown, risk: RiskMetrics, position_count: int) -> float:
        """Compute a 0–100 portfolio health score."""
        score = 100.0

        # Penalize over-concentration in one market
        max_market = max(alloc.forex_pct, alloc.indian_market_pct, alloc.crypto_pct, 0.01)
        if max_market > 80:
            score -= 15
        elif max_market > 60:
            score -= 8

        # Penalize high drawdown
        if risk.current_drawdown_pct < -5:
            score -= 20
        elif risk.current_drawdown_pct < -2:
            score -= 10

        # Penalize low diversification
        if risk.diversification_score < 30:
            score -= 10

        # Penalize too few or too many positions
        if position_count == 0:
            score -= 5
        elif position_count > 15:
            score -= 10

        # Reward good Sharpe
        if risk.sharpe_ratio > 1.5:
            score += 5
        elif risk.sharpe_ratio < 0:
            score -= 10

        return round(max(0, min(100, score)), 1)

    # ─── Recommendations ──────────────────────────────────────

    def _generate_recommendations(self, alloc: AllocationBreakdown, risk: RiskMetrics, health: float) -> List[str]:
        """Generate AI portfolio advisor recommendations."""
        recs = []
        if alloc.crypto_pct > 40:
            recs.append("Reduce crypto allocation to below 30% for better diversification.")
        if alloc.forex_pct > 70:
            recs.append("Consider diversifying into Indian or Crypto markets.")
        if risk.current_drawdown_pct < -3:
            recs.append("Portfolio in significant drawdown. Consider reducing position sizes.")
        if risk.sharpe_ratio < 0.5 and len(self._return_history) > 20:
            recs.append("Risk-adjusted returns are low. Review strategy selection.")
        if health < 50:
            recs.append("Portfolio health is critical. Review exposure and risk parameters.")
        if not recs:
            recs.append("Portfolio is well-balanced. No immediate action required.")
        return recs

    # ─── Stress Testing ──────────────────────────────────────

    def stress_test(self, scenario_name: Optional[str] = None) -> Dict[str, Any]:
        """Apply historical shock scenarios to current portfolio."""
        snapshot = self._snapshot or self.build_snapshot()
        results = {}

        scenarios = {scenario_name: self._stress_scenarios[scenario_name]} if scenario_name and scenario_name in self._stress_scenarios else self._stress_scenarios

        for name, shocks in scenarios.items():
            forex_loss = snapshot.allocation.forex_pct / 100 * shocks.get("forex", 0) * snapshot.total_equity
            metals_loss = (snapshot.allocation.by_sector.get("Metals", 0) / 100) * shocks.get("metals", 0) * snapshot.total_equity
            indices_loss = (snapshot.allocation.by_sector.get("Indices", 0) / 100) * shocks.get("indices", 0) * snapshot.total_equity
            crypto_loss = snapshot.allocation.crypto_pct / 100 * shocks.get("crypto", 0) * snapshot.total_equity
            total_impact = forex_loss + metals_loss + indices_loss + crypto_loss

            results[name] = {
                "total_impact_usd": round(total_impact, 2),
                "impact_pct": round(total_impact / max(snapshot.total_equity, 1) * 100, 2),
                "surviving_equity": round(snapshot.total_equity + total_impact, 2),
            }

        return results

    # ─── Scenario Analysis ────────────────────────────────────

    def scenario_what_if(self, add_symbol: str, market: str, notional_usd: float) -> Dict[str, Any]:
        """What-if: simulate adding a position and see impact on allocations."""
        snapshot = self._snapshot or self.build_snapshot()
        new_equity = snapshot.total_equity + notional_usd * 0.01  # Margin approximation

        market_map = {"forex": "forex_pct", "indian": "indian_market_pct", "crypto": "crypto_pct"}
        field_name = market_map.get(market, "forex_pct")
        current_pct = getattr(snapshot.allocation, field_name, 0)
        added_exposure = notional_usd / max(new_equity, 1) * 100
        new_pct = current_pct + added_exposure

        return {
            "symbol": add_symbol,
            "current_market_pct": round(current_pct, 2),
            "projected_market_pct": round(new_pct, 2),
            "risk_warning": new_pct > 50,
            "recommendation": "Acceptable" if new_pct <= 50 else "Over-concentrated — consider reducing.",
        }

    # ─── Convenience ──────────────────────────────────────────

    def get_snapshot(self) -> Dict[str, Any]:
        """Return the latest snapshot as a dict, rebuilding if stale."""
        snap = self._snapshot or self.build_snapshot()
        return snap.to_dict()


# Singleton
portfolio_intel = PortfolioIntelligence()
