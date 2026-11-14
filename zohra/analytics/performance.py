"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — PERFORMANCE ANALYTICS ENGINE         ║
║  Win Rate, Profit Factor, Expectancy, Sharpe,        ║
║  Drawdown, Session/Pair/Strategy Analysis            ║
╚══════════════════════════════════════════════════════╝
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("zohra.analytics")


class PerformanceAnalytics:
    """
    Calculates all performance metrics from raw trade data.
    Input: list of trade dicts from database
    Output: structured metrics dicts
    """

    # ─── Core Metrics ──────────────────────────────────────

    def win_rate(self, trades: List[Dict]) -> float:
        """Win rate as percentage (0-100)."""
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if (t.get('pnl_usd') or 0) > 0)
        return round(wins / len(closed) * 100, 2)

    def profit_factor(self, trades: List[Dict]) -> float:
        """
        Gross Profit / Gross Loss.
        > 1.5 = good, > 2.0 = excellent
        """
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        gross_profit = sum((t.get('pnl_usd') or 0) for t in closed if (t.get('pnl_usd') or 0) > 0)
        gross_loss   = abs(sum((t.get('pnl_usd') or 0) for t in closed if (t.get('pnl_usd') or 0) < 0))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 3)

    def expectancy(self, trades: List[Dict]) -> float:
        """
        Expected value per trade in USD.
        Formula: (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
        Positive = profitable system.
        """
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        if not closed:
            return 0.0

        wins   = [t for t in closed if (t.get('pnl_usd') or 0) > 0]
        losses = [t for t in closed if (t.get('pnl_usd') or 0) < 0]

        wr   = len(wins) / len(closed)
        lr   = 1 - wr
        avg_win  = sum(t.get('pnl_usd', 0) for t in wins)  / len(wins)  if wins   else 0
        avg_loss = abs(sum(t.get('pnl_usd', 0) for t in losses)) / len(losses) if losses else 0

        return round((wr * avg_win) - (lr * avg_loss), 2)

    def max_drawdown(self, equity_curve: List[Dict]) -> Tuple[float, float]:
        """
        Maximum drawdown from equity curve.
        Returns (max_dd_usd, max_dd_pct).
        """
        if not equity_curve:
            return 0.0, 0.0

        equities = [float(e.get('equity', 0)) for e in equity_curve]
        peak     = equities[0]
        max_dd   = 0.0
        max_peak = peak

        for eq in equities:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
            if eq > max_peak:
                max_peak = eq

        max_dd_pct = (max_dd / max_peak * 100) if max_peak > 0 else 0
        return round(max_dd, 2), round(max_dd_pct, 3)

    def sharpe_ratio(self, trades: List[Dict],
                     risk_free_rate_daily: float = 0.0) -> float:
        """
        Annualized Sharpe Ratio.
        Uses daily P&L returns, annualized by √252.
        """
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        if len(closed) < 5:
            return 0.0

        # Group by day
        daily_pnl: Dict[str, float] = {}
        for t in closed:
            ts = t.get('timestamp_close', '')
            day = ts[:10] if ts else 'unknown'
            daily_pnl[day] = daily_pnl.get(day, 0) + (t.get('pnl_usd') or 0)

        returns = list(daily_pnl.values())
        if len(returns) < 2:
            return 0.0

        mean_return = sum(returns) / len(returns)
        variance    = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        std_dev     = math.sqrt(variance) if variance > 0 else 1e-9

        sharpe = (mean_return - risk_free_rate_daily) / std_dev * math.sqrt(252)
        return round(sharpe, 3)

    def avg_trade_duration(self, trades: List[Dict]) -> float:
        """Average trade duration in minutes."""
        closed = [t for t in trades
                  if t.get('duration_minutes') and t.get('timestamp_close')]
        if not closed:
            return 0.0
        total = sum(t.get('duration_minutes', 0) for t in closed)
        return round(total / len(closed), 1)

    def calmar_ratio(self, trades: List[Dict],
                     equity_curve: List[Dict]) -> float:
        """
        Annualized Return / Max Drawdown.
        Higher = better risk-adjusted return.
        """
        if not trades or not equity_curve:
            return 0.0
        total_pnl = sum((t.get('pnl_usd') or 0) for t in trades
                        if t.get('pnl_usd') is not None)
        _, max_dd_pct = self.max_drawdown(equity_curve)
        if max_dd_pct == 0:
            return float('inf') if total_pnl > 0 else 0.0
        return round(total_pnl / (max_dd_pct / 100), 2)

    def consecutive_losses(self, trades: List[Dict]) -> int:
        """Maximum consecutive losing streak."""
        closed = sorted(
            [t for t in trades if t.get('pnl_usd') is not None and t.get('timestamp_close')],
            key=lambda x: x.get('timestamp_close', '')
        )
        max_streak = streak = 0
        for t in closed:
            if (t.get('pnl_usd') or 0) < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    def recovery_factor(self, trades: List[Dict],
                        equity_curve: List[Dict]) -> float:
        """Net profit / Max drawdown — measures recovery ability."""
        net_profit = sum((t.get('pnl_usd') or 0) for t in trades
                         if t.get('pnl_usd') is not None)
        max_dd, _ = self.max_drawdown(equity_curve)
        if max_dd == 0:
            return float('inf') if net_profit > 0 else 0.0
        return round(net_profit / max_dd, 3)

    # ─── Session Analytics ─────────────────────────────────

    def session_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down performance by trading session.
        Returns dict keyed by session name.
        """
        sessions: Dict[str, List] = {}
        for t in trades:
            if t.get('pnl_usd') is None:
                continue
            sess = t.get('session', 'Unknown') or 'Unknown'
            sessions.setdefault(sess, []).append(t)

        result = {}
        for sess, sess_trades in sessions.items():
            result[sess] = self._compute_group_stats(sess_trades)
        return result

    def pair_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Break down performance by symbol/pair."""
        pairs: Dict[str, List] = {}
        for t in trades:
            if t.get('pnl_usd') is None:
                continue
            sym = t.get('symbol', 'Unknown') or 'Unknown'
            pairs.setdefault(sym, []).append(t)

        result = {}
        for sym, sym_trades in pairs.items():
            result[sym] = self._compute_group_stats(sym_trades)
        return result

    def strategy_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Break down performance by strategy."""
        strategies: Dict[str, List] = {}
        for t in trades:
            if t.get('pnl_usd') is None:
                continue
            strat = t.get('strategy_used', 'Unknown') or 'Unknown'
            strategies.setdefault(strat, []).append(t)

        result = {}
        for strat, strat_trades in strategies.items():
            result[strat] = self._compute_group_stats(strat_trades)
        return result

    def regime_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """Break down by market regime."""
        regimes: Dict[str, List] = {}
        for t in trades:
            if t.get('pnl_usd') is None:
                continue
            regime = t.get('market_regime', 'Unknown') or 'Unknown'
            regimes.setdefault(regime, []).append(t)
        return {r: self._compute_group_stats(rt) for r, rt in regimes.items()}

    # ─── Grade Analytics ─────────────────────────────────

    def grade_performance(self, trades: List[Dict]) -> Dict[str, Dict]:
        """
        Break down performance by trade quality grade (A+, A, B, C).
        Returns per-grade metrics:
          - Win Rate
          - Profit Factor
          - Expectancy
          - Average R-Multiple
          - Expected Value
          - Total P&L
          - Average Drawdown
        """
        grades: Dict[str, List] = {}
        for t in trades:
            if t.get('pnl_usd') is None:
                continue
            g = t.get('quality_grade', 'Unknown') or 'Unknown'
            grades.setdefault(g, []).append(t)

        result = {}
        for g, g_trades in grades.items():
            stats = self._compute_group_stats(g_trades)

            # Compute average R-multiple
            r_multiples = []
            for t in g_trades:
                risk_usd = t.get('risk_usd')
                pnl = t.get('pnl_usd', 0) or 0
                if risk_usd and risk_usd > 0:
                    r_multiples.append(pnl / risk_usd)

            avg_r = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
            expected_value = stats.get('expectancy', 0.0)

            stats['avg_r_multiple'] = round(avg_r, 3)
            stats['expected_value'] = round(expected_value, 2)
            stats['grade'] = g
            result[g] = stats

        return result

    # ─── Full Report ───────────────────────────────────────

    def full_performance_report(self, trades: List[Dict],
                                equity_curve: List[Dict],
                                period: str = "All Time") -> Dict:
        """
        Master report combining all metrics.
        Returns a comprehensive analytics dict.
        """
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        wins   = [t for t in closed if (t.get('pnl_usd') or 0) > 0]
        losses = [t for t in closed if (t.get('pnl_usd') or 0) < 0]

        total_pnl  = sum((t.get('pnl_usd') or 0) for t in closed)
        avg_win    = sum(t.get('pnl_usd', 0) for t in wins) / len(wins) if wins else 0
        avg_loss   = abs(sum(t.get('pnl_usd', 0) for t in losses)) / len(losses) if losses else 0
        max_dd_usd, max_dd_pct = self.max_drawdown(equity_curve)

        # Best/worst pairs
        pair_stats = self.pair_performance(trades)
        best_pair  = max(pair_stats, key=lambda k: pair_stats[k]['total_pnl'], default="")
        worst_pair = min(pair_stats, key=lambda k: pair_stats[k]['total_pnl'], default="")

        # Best session
        sess_stats  = self.session_performance(trades)
        best_session = max(sess_stats, key=lambda k: sess_stats[k]['win_rate'], default="")

        # Grade analytics
        grade_stats = self.grade_performance(trades)

        report = {
            "period":               period,
            "generated_at":         datetime.utcnow().isoformat(),

            # Volume
            "total_trades":         len(closed),
            "winning_trades":       len(wins),
            "losing_trades":        len(losses),
            "open_trades":          len(trades) - len(closed),

            # Core metrics
            "win_rate":             self.win_rate(trades),
            "profit_factor":        self.profit_factor(trades),
            "expectancy":           self.expectancy(trades),
            "sharpe_ratio":         self.sharpe_ratio(trades),

            # P&L
            "total_pnl":            round(total_pnl, 2),
            "avg_pnl":              round(total_pnl / len(closed), 2) if closed else 0,
            "avg_win":              round(avg_win, 2),
            "avg_loss":             round(avg_loss, 2),
            "largest_win":          round(max((t.get('pnl_usd') or 0) for t in closed), 2) if closed else 0,
            "largest_loss":         round(min((t.get('pnl_usd') or 0) for t in closed), 2) if closed else 0,

            # Risk metrics
            "max_drawdown_usd":     max_dd_usd,
            "max_drawdown_pct":     max_dd_pct,
            "max_consecutive_losses": self.consecutive_losses(trades),
            "recovery_factor":      self.recovery_factor(trades, equity_curve),
            "calmar_ratio":         self.calmar_ratio(trades, equity_curve),

            # Duration
            "avg_duration_minutes": self.avg_trade_duration(trades),

            # Breakdowns
            "best_pair":            best_pair,
            "worst_pair":           worst_pair,
            "best_session":         best_session,
            "session_stats":        sess_stats,
            "pair_stats":           pair_stats,
            "strategy_stats":       self.strategy_performance(trades),
            "regime_stats":         self.regime_performance(trades),
            "grade_stats":          grade_stats,
        }
        return report

    # ─── Rejection Analysis ────────────────────────────────

    def analyze_rejections(self, rejections: List[Dict]) -> Dict:
        """
        Analyze patterns in rejected trades to guide parameter tuning.
        Ported from trading_bot2's get_rejection_analysis().
        """
        if not rejections:
            return {"message": "No rejections recorded yet"}

        total = len(rejections)
        struct_fails = sum(1 for r in rejections if not r.get('structure_pass'))
        liq_fails    = sum(1 for r in rejections if not r.get('liquidity_pass'))
        mom_fails    = sum(1 for r in rejections if not r.get('momentum_pass'))
        vol_fails    = sum(1 for r in rejections if not r.get('volume_pass'))

        # Most common rejection reason
        reasons: Dict[str, int] = {}
        for r in rejections:
            reason = r.get('reason_for_rejection', 'Unknown')
            # Shorten to category
            key = reason.split(':')[0].strip() if ':' in reason else reason[:40]
            reasons[key] = reasons.get(key, 0) + 1

        top_reasons = sorted(reasons.items(), key=lambda x: x[1], reverse=True)[:5]

        # Most common regime for rejections
        regimes: Dict[str, int] = {}
        for r in rejections:
            reg = r.get('regime', 'unknown') or 'unknown'
            regimes[reg] = regimes.get(reg, 0) + 1

        worst_regime = max(regimes, key=regimes.get) if regimes else "unknown"

        # Recommendation
        fails = {
            "Structure": struct_fails, "Liquidity": liq_fails,
            "Momentum":  mom_fails,    "Volume":    vol_fails
        }
        worst_filter = max(fails, key=fails.get)
        worst_pct    = fails[worst_filter] / total * 100 if total > 0 else 0

        if worst_pct > 50:
            recommendation = (f"Focus on {worst_filter}: {worst_pct:.0f}% of rejections fail this filter. "
                              f"Consider loosening {worst_filter.lower()} parameters.")
        else:
            recommendation = "Filters are balanced. Current settings look calibrated."

        return {
            "total_rejected":        total,
            "structure_fail_rate":   f"{struct_fails/total*100:.1f}%",
            "liquidity_fail_rate":   f"{liq_fails/total*100:.1f}%",
            "momentum_fail_rate":    f"{mom_fails/total*100:.1f}%",
            "volume_fail_rate":      f"{vol_fails/total*100:.1f}%",
            "top_rejection_reasons": top_reasons,
            "worst_regime":          worst_regime,
            "regime_breakdown":      regimes,
            "recommendation":        recommendation,
        }

    # ─── Helper ────────────────────────────────────────────

    def _compute_group_stats(self, trades: List[Dict]) -> Dict:
        """Compute standard stats for a group of trades."""
        if not trades:
            return {}
        closed = [t for t in trades if t.get('pnl_usd') is not None]
        wins   = [t for t in closed if (t.get('pnl_usd') or 0) > 0]
        total_pnl = sum((t.get('pnl_usd') or 0) for t in closed)
        avg_win  = sum(t.get('pnl_usd', 0) for t in wins) / len(wins) if wins else 0
        avg_loss_list = [t for t in closed if (t.get('pnl_usd') or 0) < 0]
        avg_loss = abs(sum(t.get('pnl_usd', 0) for t in avg_loss_list)) / len(avg_loss_list) if avg_loss_list else 0
        wr       = len(wins) / len(closed) * 100 if closed else 0
        pf       = self.profit_factor(closed)
        exp      = self.expectancy(closed)
        avg_rr   = sum((t.get('risk_reward_ratio') or 0) for t in closed) / len(closed) if closed else 0

        return {
            "total_trades": len(closed),
            "wins":         len(wins),
            "losses":       len(avg_loss_list),
            "win_rate":     round(wr, 2),
            "profit_factor": pf,
            "expectancy":   exp,
            "total_pnl":    round(total_pnl, 2),
            "avg_win":      round(avg_win, 2),
            "avg_loss":     round(avg_loss, 2),
            "avg_rr":       round(avg_rr, 2),
        }

    def daily(self) -> Dict:
        """
        Return daily statistics for today's trades.
        """
        from zohra.db.schema import db
        # Get trades closed in the last 1 day
        closed_trades = db.get_closed_trades(limit=100, days=1)
        # We can calculate daily stats
        wins = [t for t in closed_trades if (t.get('pnl_usd') or 0) > 0]
        losses = [t for t in closed_trades if (t.get('pnl_usd') or 0) < 0]
        total_pnl = sum((t.get('pnl_usd') or 0) for t in closed_trades)
        wr = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0
        
        return {
            "total_trades": len(closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(wr, 2),
            "net_pnl": round(total_pnl, 2),
            "total_pnl": round(total_pnl, 2)
        }



# Singleton
analytics = PerformanceAnalytics()
