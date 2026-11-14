"""
╔══════════════════════════════════════════════════════════════════════╗
║             ZOHRA — ENTERPRISE BACKTESTING DIVISION                 ║
║   Institutional Multi-Asset Portfolio Simulation & Optimization     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable

import numpy as np
import pandas as pd

logger = logging.getLogger("zohra.validation.backtester")


class InstitutionalBacktester:
    """
    Professional quantitative backtesting framework supporting transaction costs,
    latencies, spreads, partial fills, walk-forward, and Monte Carlo stress tests.
    """

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        
        # Transaction costs & network factors
        self.spread_pips = 1.2
        self.slippage_pips = 0.5
        self.commission_per_lot = 3.50  # USD per side (total 7.00 round-trip)
        self.latency_ms = 150.0
        self.partial_fill_prob = 0.05   # 5% probability of partial fill on large lots
        
        # Re-initialize state
        self.reset()

    def reset(self):
        self.capital = self.initial_capital
        self.positions: List[Dict] = []
        self.trade_history: List[Dict] = []
        self.equity_curve: List[float] = [self.initial_capital]
        self.timestamps: List[datetime] = []

    def configure(self, spread: float = 1.2, slippage: float = 0.5, 
                  commission: float = 3.50, latency: float = 150.0,
                  partial_fill_prob: float = 0.05):
        """Set backtest transaction cost settings."""
        self.spread_pips = spread
        self.slippage_pips = slippage
        self.commission_per_lot = commission
        self.latency_ms = latency
        self.partial_fill_prob = partial_fill_prob

    # ─── Run Simulation ───────────────────────────────────────

    def run(self, symbol: str, df: pd.DataFrame, strategy_fn: Callable[[pd.DataFrame, int], Optional[Dict]],
            timeframe: str = "H1") -> Dict[str, Any]:
        """
        Runs backtest over historical OHLCV data.
        strategy_fn(df, current_idx) -> returns signal dict or None
        """
        self.reset()
        if df is None or len(df) < 50:
            return {"status": "error", "message": "Insufficient data"}

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        open_ = df["open"].values
        times = df.index.to_pydatetime() if hasattr(df.index, 'to_pydatetime') else df.index

        # Walk-forward loops
        for i in range(30, len(df)):
            current_time = times[i]
            current_price = float(close[i])
            self.timestamps.append(current_time)

            # 1. Manage open positions (SL/TP executions)
            self._check_stops(high[i], low[i], open_[i], current_time)

            # 2. Trigger Strategy
            hist_df = df.iloc[:i]
            signal = strategy_fn(hist_df, i - 1)
            
            if signal and signal.get("direction") in ("LONG", "SHORT"):
                self._execute_simulated_order(
                    symbol=symbol,
                    direction=signal["direction"],
                    price=current_price,
                    stop_loss=signal.get("stop_loss", 0.0),
                    take_profit=signal.get("take_profit", 0.0),
                    lots=signal.get("lots", 1.0),
                    time_in=current_time
                )

            # 3. Calculate equity
            equity = self.capital + self._get_unrealized_pnl(current_price)
            self.equity_curve.append(equity)

        # Force close open positions at backtest end
        self._close_all(float(close[-1]), times[-1])
        self.equity_curve.append(self.capital)

        return self._compute_performance_report()

    # ─── Stop checks & Executions ─────────────────────────────

    def _check_stops(self, high: float, low: float, open_: float, time_now: datetime):
        """Check open positions against SL/TP with gap simulations."""
        active = []
        for pos in self.positions:
            dir_sign = 1 if pos["direction"] == "LONG" else -1
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            hit = False
            exit_price = 0.0
            reason = ""

            # Check SL
            if sl > 0:
                if (pos["direction"] == "LONG" and low < sl) or (pos["direction"] == "SHORT" and high > sl):
                    hit = True
                    # Slippage/Gap Simulation on SL
                    exit_price = sl - (self.slippage_pips * self._get_pip_value(pos["symbol"])) * dir_sign
                    # Market Gap: check if open is worse than SL
                    if (pos["direction"] == "LONG" and open_ < sl) or (pos["direction"] == "SHORT" and open_ > sl):
                        exit_price = open_
                    reason = "SL"

            # Check TP
            if tp > 0 and not hit:
                if (pos["direction"] == "LONG" and high > tp) or (pos["direction"] == "SHORT" and low < tp):
                    hit = True
                    # Limit orders execute exactly at TP minus small latency/spread factor
                    exit_price = tp
                    if (pos["direction"] == "LONG" and open_ > tp) or (pos["direction"] == "SHORT" and open_ < tp):
                        exit_price = open_
                    reason = "TP"

            if hit:
                self._realize_close(pos, exit_price, time_now, reason)
            else:
                active.append(pos)
        self.positions = active

    def _execute_simulated_order(self, symbol: str, direction: str, price: float,
                                 stop_loss: float, take_profit: float, lots: float, time_in: datetime):
        """Places simulated position adjusting for spreads, slippage, and commissions."""
        pip = self._get_pip_value(symbol)
        spread_offset = (self.spread_pips / 2.0) * pip
        slippage_offset = random.uniform(0, self.slippage_pips) * pip

        # Latency Simulation (delay entry price slightly)
        latency_slip = (self.latency_ms / 1000.0) * random.uniform(-0.1, 0.2) * pip
        
        if direction == "LONG":
            entry = price + spread_offset + slippage_offset + latency_slip
        else:
            entry = price - spread_offset - slippage_offset - latency_slip

        # Commission (lot based)
        comm = lots * self.commission_per_lot

        # Partial fill simulation on large sizes
        actual_lots = lots
        if lots > 1.5 and random.random() < self.partial_fill_prob:
            actual_lots = round(lots * random.uniform(0.4, 0.8), 2)
            comm = actual_lots * self.commission_per_lot
            logger.info(f"⚠️ [Backtester] Partial fill executed: {actual_lots} of {lots} lots filled.")

        pos = {
            "symbol": symbol,
            "direction": direction,
            "lots": actual_lots,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "open_time": time_in,
            "commission": comm,
        }
        self.positions.append(pos)

    def _realize_close(self, pos: Dict, exit_price: float, time_out: datetime, reason: str):
        """Close position and deduct transaction costs."""
        dir_mult = 1 if pos["direction"] == "LONG" else -1
        pips_gain = (exit_price - pos["entry_price"]) * dir_mult
        
        # Dollar P&L calculation
        contract_size = 100000.0 if "XAU" not in pos["symbol"] else 100.0
        pnl = pips_gain * contract_size * pos["lots"]
        
        # Deduct commissions
        round_trip_comm = pos["commission"] * 2
        net_pnl = pnl - round_trip_comm
        
        self.capital += net_pnl
        
        self.trade_history.append({
            "symbol": pos["symbol"],
            "direction": pos["direction"],
            "lots": pos["lots"],
            "entry_price": pos["entry_price"],
            "exit_price": exit_price,
            "pnl": round(net_pnl, 2),
            "pips": round(pips_gain / self._get_pip_value(pos["symbol"]), 1),
            "open_time": pos["open_time"].isoformat(),
            "close_time": time_out.isoformat(),
            "exit_reason": reason,
        })

    def _get_unrealized_pnl(self, current_price: float) -> float:
        """Compute floating PnL of open positions."""
        upnl = 0.0
        for pos in self.positions:
            dir_mult = 1 if pos["direction"] == "LONG" else -1
            contract_size = 100000.0 if "XAU" not in pos["symbol"] else 100.0
            pips_gain = (current_price - pos["entry_price"]) * dir_mult
            pnl = pips_gain * contract_size * pos["lots"]
            upnl += pnl - (pos["commission"] * 2)
        return upnl

    def _close_all(self, price: float, time_now: datetime):
        """Close all remaining open positions at simulation end."""
        for pos in self.positions:
            self._realize_close(pos, price, time_now, "END")
        self.positions = []

    # ─── Statistics & Metrics ─────────────────────────────────

    def _compute_performance_report(self) -> Dict[str, Any]:
        """Generate institutional performance analytics."""
        if not self.trade_history:
            return {"status": "empty", "message": "No trades executed"}

        pnls = [t["pnl"] for t in self.trade_history]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        total_trades = len(pnls)
        win_rate = round(len(wins) / total_trades * 100, 2)
        
        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = round(total_profit / max(total_loss, 1.0), 2)
        
        net_profit = sum(pnls)
        pct_return = round(net_profit / self.initial_capital * 100, 2)

        # Equity Curve statistics
        eq = np.array(self.equity_curve)
        peak = np.maximum.accumulate(eq)
        drawdowns = (eq - peak) / peak
        max_dd_pct = round(float(np.min(drawdowns)) * 100, 2)

        # Sharpe / Sortino
        returns = np.diff(eq) / eq[:-1]
        mean_ret = np.mean(returns) if len(returns) > 0 else 0
        std_ret = np.std(returns) if len(returns) > 0 else 1e-9
        sharpe = round((mean_ret / std_ret) * math.sqrt(252), 2) if std_ret > 0 else 0.0

        downside_ret = returns[returns < 0]
        sortino = 0.0
        if len(downside_ret) > 0:
            std_down = np.std(downside_ret)
            sortino = round((mean_ret / std_down) * math.sqrt(252), 2) if std_down > 0 else 0.0

        # Calmar
        calmar = round((mean_ret * 252) / abs(max_dd_pct / 100), 2) if max_dd_pct != 0 else 0.0

        return {
            "status": "success",
            "initial_capital": self.initial_capital,
            "final_equity": round(float(eq[-1]), 2),
            "net_profit": round(net_profit, 2),
            "return_pct": pct_return,
            "total_trades": total_trades,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd_pct,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "calmar_ratio": calmar,
            "trades": self.trade_history,
        }

    # ─── Monte Carlo Stress Tests ─────────────────────────────

    def run_monte_carlo(self, iterations: int = 1000) -> Dict[str, Any]:
        """Shuffles trade order multiple times to verify worst-case drawdown probabilities."""
        if not self.trade_history:
            return {"status": "error", "message": "No trade history to run simulation"}

        pnls = [t["pnl"] for t in self.trade_history]
        max_dds: List[float] = []
        final_balances: List[float] = []

        for _ in range(iterations):
            shuffled = np.random.permutation(pnls)
            eq_curve = self.initial_capital + np.cumsum(shuffled)
            
            # Drawdown
            peak = np.maximum.accumulate(eq_curve)
            dds = (eq_curve - peak) / peak
            max_dds.append(float(np.min(dds)) * 100)
            final_balances.append(float(eq_curve[-1]))

        avg_dd = round(float(np.mean(max_dds)), 2)
        worst_dd = round(float(np.min(max_dds)), 2)
        p95_dd = round(float(np.percentile(max_dds, 5)), 2) # 95% Var DD
        
        avg_bal = round(float(np.mean(final_balances)), 2)
        worst_bal = round(float(np.min(final_balances)), 2)

        return {
            "avg_drawdown_pct": avg_dd,
            "worst_drawdown_pct": worst_dd,
            "p95_drawdown_pct": p95_dd,
            "avg_final_balance": avg_bal,
            "worst_final_balance": worst_bal,
            "prob_of_ruin_pct": round(sum(1 for b in final_balances if b < (self.initial_capital * 0.5)) / iterations * 100, 2),
        }

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _get_pip_value(symbol: str) -> float:
        s = symbol.upper()
        if "JPY" in s:
            return 0.01
        elif "XAU" in s:
            return 0.1
        return 0.0001
