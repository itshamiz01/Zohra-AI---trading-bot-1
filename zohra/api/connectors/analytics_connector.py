import logging
from typing import Dict, Any, Optional
from zohra.db.schema import db
from zohra.analytics.performance import analytics

logger = logging.getLogger("zohra.api.connectors.analytics")

class AnalyticsConnector:
    """
    Analytics connector translating historical trade and equity snapshots
    into structured quantitative reports (expectancy, profit factor, drawdown, Setup Ratios).
    """

    def get_performance_summary(self, days: int = 30) -> Dict[str, Any]:
        """Generate comprehensive performance report including win rate, profit factor, Calmar, and Sharpe."""
        try:
            trades = db.get_closed_trades(limit=1000, days=days)
            equity_curve = db.get_equity_curve(days=days)
            
            # If no trades closed, provide a blank default
            if not trades:
                return {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "expectancy": 0.0,
                    "total_pnl": 0.0,
                    "max_drawdown_usd": 0.0,
                    "max_drawdown_pct": 0.0,
                    "best_pair": "None",
                    "worst_pair": "None",
                    "sharpe_ratio": 0.0,
                    "calmar_ratio": 0.0
                }
            
            report = analytics.full_performance_report(
                trades=trades,
                equity_curve=equity_curve,
                period=f"Last {days} Days"
            )
            return report
        except Exception as e:
            logger.error(f"Error compiling performance summary: {e}")
            return {"error": str(e)}

    def get_setup_performance(self, days: int = 30) -> Dict[str, Any]:
        """Determine the best and worst performing setups (symbols and strategies)."""
        try:
            summary = self.get_performance_summary(days=days)
            if "error" in summary or summary.get("total_trades", 0) == 0:
                return {
                    "best_pair": "None",
                    "worst_pair": "None",
                    "best_session": "None",
                    "best_strategy": "None",
                    "worst_strategy": "None"
                }

            strategy_stats = summary.get("strategy_stats", {})
            best_strat = "None"
            worst_strat = "None"
            
            if strategy_stats:
                best_strat = max(strategy_stats, key=lambda k: strategy_stats[k].get("total_pnl", 0.0), default="None")
                worst_strat = min(strategy_stats, key=lambda k: strategy_stats[k].get("total_pnl", 0.0), default="None")

            return {
                "best_pair": summary.get("best_pair", "None"),
                "worst_pair": summary.get("worst_pair", "None"),
                "best_session": summary.get("best_session", "None"),
                "best_strategy": best_strat,
                "worst_strategy": worst_strat
            }
        except Exception as e:
            logger.error(f"Error compiling setup performance: {e}")
            return {"error": str(e)}
