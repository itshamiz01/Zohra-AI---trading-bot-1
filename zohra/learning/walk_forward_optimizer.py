"""
Zohra Walk-Forward Parameter Optimizer.
Runs parameter grid searches on weekends when markets are closed to find optimal weights.
"""

import logging
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any

from zohra.db.schema import db
from zohra.config.settings import STATE, settings

logger = logging.getLogger("zohra.optimizer")

class WalkForwardOptimizer:
    """
    Self-contained parameter optimization engine.
    Analyzes historical trade metrics and searches for scoring weights that maximize profit factor and expectancy.
    """

    def __init__(self):
        self.optimizer_run_id = ""

    def run_optimization_cycle(self, days: int = 45) -> Dict[str, Any]:
        """
        Run a walk-forward parameter sweep over the last N days of trading data.
        """
        self.optimizer_run_id = f"OPT_{int(time.time())}"
        logger.info(f"⚡ Starting Walk-Forward Optimization Cycle {self.optimizer_run_id} over last {days} days")
        
        # 1. Fetch closed trades from DB
        trades = db.get_closed_trades(limit=500)
        # Filter trades within the requested days window manually
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        trades = [t for t in trades if t.get("timestamp_close") and t["timestamp_close"] >= cutoff_date]
        
        if len(trades) < 5:
            logger.warning(f"Optimization skipped: Insufficient trades (found {len(trades)} closed trades in the last {days} days, need at least 5)")
            return {"status": "skipped", "reason": "Insufficient trades"}

        # 2. Extract features from trades (e.g. breakdown scores and outcome P&L)
        trade_data = []
        for t in trades:
            scores = {
                "structure": t.get("score_structure", 0) or 0,
                "liquidity": t.get("score_liquidity", 0) or 0,
                "smc": t.get("score_smc", 0) or 0,
                "trend": t.get("score_trend", 0) or 0,
                "momentum": t.get("score_momentum", 0) or 0,
                "volatility": t.get("score_volatility", 0) or 0,
                "pullback": t.get("score_pullback", 0) or 0
            }
            
            trade_data.append({
                "symbol": t.get("symbol"),
                "direction": t.get("direction"),
                "pnl_usd": t.get("pnl_usd") or t.get("profit_loss", 0.0) or 0.0,
                "scores": scores
            })

        # 3. Parameter sweep
        # We test different weight profiles.
        weight_profiles = [
            # Profile 1: Default / SMC-heavy
            {"structure": 0.20, "liquidity": 0.15, "smc": 0.25, "trend": 0.15, "momentum": 0.10, "volatility": 0.05, "pullback": 0.10},
            # Profile 2: Trend / Momentum-heavy
            {"structure": 0.15, "liquidity": 0.10, "smc": 0.10, "trend": 0.30, "momentum": 0.20, "volatility": 0.05, "pullback": 0.10},
            # Profile 3: Liquidity / Volume-heavy
            {"structure": 0.10, "liquidity": 0.30, "smc": 0.20, "trend": 0.10, "momentum": 0.10, "volatility": 0.10, "pullback": 0.10},
            # Profile 4: Equal weights
            {"structure": 0.14, "liquidity": 0.14, "smc": 0.14, "trend": 0.14, "momentum": 0.14, "volatility": 0.15, "pullback": 0.15},
            # Profile 5: Structure & Liquidity focused
            {"structure": 0.25, "liquidity": 0.25, "smc": 0.15, "trend": 0.10, "momentum": 0.10, "volatility": 0.05, "pullback": 0.10}
        ]

        best_profile = None
        best_expectancy = -9999.0
        best_metrics = {}

        for profile in weight_profiles:
            simulated_trades = []
            for td in trade_data:
                # Calculate new simulated score
                sim_score = sum(profile[cat] * td["scores"][cat] for cat in profile)
                
                # Map to hypothetical grade
                if sim_score >= 85:
                    grade = "A+"
                    mult = 1.0
                elif sim_score >= 75:
                    grade = "A"
                    mult = 1.0
                elif sim_score >= 65:
                    grade = "B"
                    mult = 0.50
                elif sim_score >= 55:
                    grade = "C"
                    mult = 0.25
                else:
                    grade = "REJECT"
                    mult = 0.0
                
                # If trade is approved under this profile
                if grade != "REJECT":
                    simulated_trades.append({
                        "pnl": td["pnl_usd"] * mult,
                        "grade": grade
                    })
            
            # Compute expectancy of simulated trades
            if simulated_trades:
                wins = [t["pnl"] for t in simulated_trades if t["pnl"] > 0]
                losses = [t["pnl"] for t in simulated_trades if t["pnl"] < 0]
                total = len(simulated_trades)
                
                win_rate = len(wins) / total if total > 0 else 0
                avg_win = sum(wins) / len(wins) if wins else 0
                avg_loss = sum(losses) / len(losses) if losses else 0
                
                expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
                profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else (sum(wins) if wins else 1.0)
                
                metrics = {
                    "win_rate": win_rate,
                    "expectancy": expectancy,
                    "profit_factor": profit_factor,
                    "trades": total
                }
                
                if expectancy > best_expectancy:
                    best_expectancy = expectancy
                    best_profile = profile
                    best_metrics = metrics
                    
        if best_profile:
            # 4. Save recommendation to DB
            recom_text = f"Optimize trade scoring weights: structure={best_profile['structure']:.2f}, liquidity={best_profile['liquidity']:.2f}, smc={best_profile['smc']:.2f}, trend={best_profile['trend']:.2f}, momentum={best_profile['momentum']:.2f}, volatility={best_profile['volatility']:.2f}, pullback={best_profile['pullback']:.2f}"
            evidence = json.dumps({
                "optimizer_run_id": self.optimizer_run_id,
                "days_analyzed": days,
                "historical_expectancy_usd": round(best_expectancy, 2),
                "historical_profit_factor": round(best_metrics["profit_factor"], 2),
                "simulated_trades_count": best_metrics["trades"]
            })
            
            self._save_recommendation(recom_text, evidence)
            self._log_strategy_evolution(best_profile)
            
            logger.info(f"🏆 Walk-Forward Optimizer completed. Best expectancy: ${best_expectancy:.2f}. Recommended weights: {best_profile}")
            return {
                "status": "success",
                "optimizer_run_id": self.optimizer_run_id,
                "best_weights": best_profile,
                "metrics": best_metrics
            }
        
        return {"status": "failed", "reason": "No optimal profile found"}

    def _save_recommendation(self, text: str, evidence: str):
        try:
            db._execute("""
                INSERT INTO learning_recommendations (created_at, category, recommendation_text, supporting_evidence, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (datetime.utcnow().isoformat(), "WALK_FORWARD_OPTIMIZER", text, evidence))
        except Exception as e:
            logger.error(f"Error saving optimizer recommendation: {e}")

    def _log_strategy_evolution(self, weights: Dict[str, float]):
        try:
            db._execute("""
                INSERT INTO strategy_evolution_history (timestamp, strategy_name, parameter_updates, optimizer_run_id)
                VALUES (?, ?, ?, ?)
            """, (datetime.utcnow().isoformat(), "ZohraScoringEngine", json.dumps(weights), self.optimizer_run_id))
        except Exception as e:
            logger.error(f"Error saving strategy evolution: {e}")

# Instantiate singleton
walk_forward_optimizer = WalkForwardOptimizer()
