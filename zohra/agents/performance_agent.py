from datetime import datetime, timedelta
from typing import Dict, Any, List
from zohra.db.schema import db
from zohra.analytics.performance import analytics
from zohra.core.agent_message import AgentMessage

class PerformanceAgent:
    """
    Performance Review Agent:
    - Reviews closed trades from the database.
    - Computes performance statistics (win rates, profit factors, Sharpe ratio, max drawdown, etc.).
    - Generates actionable optimization suggestions (e.g., recommend adjusting strategy weights).
    - Saves performance snapshots to the database.
    """
    def __init__(self):
        self.db = db

    def generate_optimization_suggestions(self, closed_trades: List[Dict], rejections: List[Dict]) -> List[str]:
        """Analyzes historical statistics to suggest specific regime and strategy enhancements."""
        suggestions = []
        if not closed_trades:
            return ["No trading history available to generate optimization suggestions."]

        # Calculate strategy statistics
        strat_stats = analytics.strategy_performance(closed_trades)
        for strategy, stats in strat_stats.items():
            win_rate = stats.get("win_rate", 0)
            total_trades = stats.get("total_trades", 0)
            profit_factor = stats.get("profit_factor", 0)
            
            if total_trades >= 5:
                if win_rate < 40 or profit_factor < 1.0:
                    suggestions.append(
                        f"Strategy [{strategy}] is currently underperforming with a profit factor of {profit_factor:.2f} "
                        f"and win rate of {win_rate:.1f}% across {total_trades} trades. "
                        f"Action: Consider reducing its base weights in adaptive_scorer or disabling it in high-volatility regimes."
                    )
                elif win_rate >= 60 and profit_factor > 1.8:
                    suggestions.append(
                        f"Strategy [{strategy}] is performing exceptionally well with a profit factor of {profit_factor:.2f} "
                        f"and win rate of {win_rate:.1f}%. "
                        f"Action: Consider increasing its base weights in adaptive_scorer to capitalize on its high accuracy."
                    )

        # Analyze rejections
        rejection_analysis = analytics.analyze_rejections(rejections)
        if isinstance(rejection_analysis, dict) and "recommendation" in rejection_analysis:
            suggestions.append(f"Rejection Logger Audit: {rejection_analysis['recommendation']}")

        return suggestions

    def run_review(self, days: int = 7) -> Dict[str, Any]:
        """
        Runs the performance review process over the specified days:
        - Fetches closed trades and equity curve.
        - Calculates metrics.
        - Generates suggestions.
        - Saves the snapshot to DB.
        """
        closed_trades = self.db.get_closed_trades(limit=1000, days=days)
        equity_curve = self.db.get_equity_curve(days=days)
        rejections = self.db.get_rejections(limit=200)

        # Combine into a full report
        report = analytics.full_performance_report(closed_trades, equity_curve, period=f"{days} Days")
        
        # Add optimization suggestions
        suggestions = self.generate_optimization_suggestions(closed_trades, rejections)
        report["optimization_suggestions"] = suggestions

        # Save performance snapshot to DB
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        end_date = datetime.utcnow().isoformat()
        
        # Ensure infinity is handled safely for JSON/DB insertion
        pf = report.get("profit_factor", 1.0)
        if pf == float('inf') or pf is None:
            pf = 999.0

        snapshot = {
            "period_type": "weekly" if days == 7 else "custom",
            "period_start": start_date,
            "period_end": end_date,
            "total_trades": report.get("total_trades", 0),
            "winning_trades": report.get("winning_trades", 0),
            "losing_trades": report.get("losing_trades", 0),
            "win_rate": report.get("win_rate", 0.0),
            "profit_factor": float(pf),
            "expectancy": report.get("expectancy", 0.0),
            "total_pnl": report.get("total_pnl", 0.0),
            "max_drawdown": report.get("max_drawdown_pct", 0.0),
            "sharpe_ratio": report.get("sharpe_ratio", 0.0),
            "avg_duration_min": int(report.get("avg_duration_minutes", 0)),
            "best_pair": report.get("best_pair", ""),
            "worst_pair": report.get("worst_pair", ""),
            "best_session": report.get("best_session", ""),
            "strategy_data": {
                "suggestions": suggestions,
                "consecutive_losses": report.get("max_consecutive_losses", 0)
            }
        }
        
        self.db.save_performance_snapshot(snapshot)
        return report
