"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — AI STRATEGY OPTIMIZER                              ║
║   Self-Improving Optimization with Overfitting Protection           ║
╚══════════════════════════════════════════════════════════════════════╝

The optimizer must never overfit.
Validate every optimization before deployment.
Recommend improvements instead of blindly applying them.
"""

import logging
import uuid
import math
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from itertools import product

import numpy as np

from zohra.intelligence.models import OptimizationResult
from zohra.config.settings import INTELLIGENCE_OPTIMIZER_MAX_ITERATIONS

logger = logging.getLogger("zohra.intelligence.optimizer")


class StrategyOptimizer:
    """
    AI-driven strategy optimizer that tunes parameters using grid search,
    walk-forward optimization, and Monte Carlo validation.
    Always operates in recommend-only mode.
    """

    def __init__(self):
        self.max_iterations = INTELLIGENCE_OPTIMIZER_MAX_ITERATIONS
        self._history: List[OptimizationResult] = []

    # ─── Grid Search Optimization ─────────────────────────────

    def grid_search(self, evaluate_fn, param_grid: Dict[str, List[Any]],
                    strategy_name: str = "") -> OptimizationResult:
        """
        Exhaustive grid search over parameter combinations.
        evaluate_fn(params) -> float (Sharpe ratio or target metric)
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(product(*values))

        if len(combinations) > self.max_iterations:
            # Sample randomly
            np.random.shuffle(combinations)
            combinations = combinations[:self.max_iterations]
            logger.info(f"Grid search capped at {self.max_iterations} iterations.")

        best_score = -float("inf")
        best_params = {}

        for combo in combinations:
            params = dict(zip(keys, combo))
            try:
                score = evaluate_fn(params)
                if score > best_score:
                    best_score = score
                    best_params = params
            except Exception as e:
                logger.debug(f"Optimizer eval error: {e}")

        result = OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="grid_search",
            best_params=best_params,
            in_sample_sharpe=round(best_score, 4),
            recommendations=[f"Best parameters found: {best_params}"],
        )
        self._history.append(result)
        return result

    # ─── Walk-Forward Optimization ────────────────────────────

    def walk_forward(self, train_fn, test_fn, param_grid: Dict[str, List[Any]],
                     windows: int = 5, strategy_name: str = "") -> OptimizationResult:
        """
        Walk-forward optimization: train on window, validate on out-of-sample.
        train_fn(params, window_idx) -> float (in-sample score)
        test_fn(params, window_idx) -> float (out-of-sample score)
        """
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(product(*values))

        if len(combinations) > self.max_iterations:
            np.random.shuffle(combinations)
            combinations = combinations[:self.max_iterations]

        best_oos_total = -float("inf")
        best_is_total = -float("inf")
        best_params = {}

        for combo in combinations:
            params = dict(zip(keys, combo))
            is_scores = []
            oos_scores = []

            for w in range(windows):
                try:
                    is_score = train_fn(params, w)
                    oos_score = test_fn(params, w)
                    is_scores.append(is_score)
                    oos_scores.append(oos_score)
                except Exception:
                    pass

            if oos_scores:
                avg_oos = float(np.mean(oos_scores))
                avg_is = float(np.mean(is_scores))
                if avg_oos > best_oos_total:
                    best_oos_total = avg_oos
                    best_is_total = avg_is
                    best_params = params

        # Overfitting score: how much IS outperforms OOS
        overfitting = 0.0
        if best_is_total > 0 and best_oos_total > 0:
            overfitting = max(0, (best_is_total - best_oos_total) / max(best_is_total, 1e-9))
        overfitting = min(1.0, overfitting)

        recommendations = []
        if overfitting > 0.5:
            recommendations.append("⚠️ High overfitting detected. Parameters may not generalize well.")
        elif overfitting > 0.3:
            recommendations.append("⚠️ Moderate overfitting. Consider simplifying parameters.")
        else:
            recommendations.append("✅ Low overfitting. Parameters appear robust.")
        recommendations.append(f"Best parameters: {best_params}")

        result = OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="walk_forward",
            best_params=best_params,
            in_sample_sharpe=round(best_is_total, 4),
            out_of_sample_sharpe=round(best_oos_total, 4),
            overfitting_score=round(overfitting, 4),
            recommendations=recommendations,
            improvement_pct=round((best_oos_total - 1.0) * 100, 2) if best_oos_total > 0 else 0.0,
        )
        self._history.append(result)
        return result

    # ─── Monte Carlo Validation ───────────────────────────────

    def monte_carlo_validate(self, trade_results: List[float],
                              iterations: int = 1000, confidence: float = 0.95,
                              strategy_name: str = "") -> OptimizationResult:
        """
        Monte Carlo validation: randomize trade order to test robustness.
        trade_results: list of P&L values per trade.
        """
        if not trade_results or len(trade_results) < 10:
            return OptimizationResult(
                optimization_id=str(uuid.uuid4())[:8],
                strategy_name=strategy_name,
                method="monte_carlo",
                recommendations=["Insufficient trades for Monte Carlo validation (need >= 10)."],
            )

        original_equity = np.cumsum(trade_results)
        original_dd = self._max_drawdown(original_equity)
        original_final = float(original_equity[-1])

        mc_finals = []
        mc_dds = []

        for _ in range(iterations):
            shuffled = np.random.permutation(trade_results)
            equity = np.cumsum(shuffled)
            mc_finals.append(float(equity[-1]))
            mc_dds.append(self._max_drawdown(equity))

        # Percentile analysis
        percentile_idx = int((1 - confidence) * iterations)
        sorted_finals = sorted(mc_finals)
        worst_case = sorted_finals[percentile_idx] if percentile_idx < len(sorted_finals) else sorted_finals[0]

        # Pass if worst-case final equity is positive
        mc_pass = worst_case > 0

        avg_final = float(np.mean(mc_finals))
        avg_dd = float(np.mean(mc_dds))

        recommendations = []
        if mc_pass:
            recommendations.append(f"✅ Monte Carlo PASSED. {confidence * 100:.0f}% confidence floor: ${worst_case:.2f}")
        else:
            recommendations.append(f"❌ Monte Carlo FAILED. {confidence * 100:.0f}% confidence floor: ${worst_case:.2f}")
        recommendations.append(f"Average final equity: ${avg_final:.2f} | Avg max DD: {avg_dd:.2f}%")

        result = OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="monte_carlo",
            monte_carlo_pass=mc_pass,
            best_params={"iterations": iterations, "confidence": confidence},
            in_sample_sharpe=round(original_final, 2),
            recommendations=recommendations,
        )
        self._history.append(result)
        return result

    # ─── Quick Optimize ───────────────────────────────────────

    def quick_optimize(self, strategy_name: str, current_params: Dict[str, Any]) -> OptimizationResult:
        """
        Quick parameter neighborhood search for common strategy parameters.
        Generates parameter grid around current values and evaluates.
        """
        param_grid: Dict[str, List[Any]] = {}

        for key, val in current_params.items():
            if isinstance(val, (int, float)):
                # Create ±20% range with 5 steps
                low = val * 0.8
                high = val * 1.2
                if isinstance(val, int):
                    steps = [int(low + (high - low) * i / 4) for i in range(5)]
                    param_grid[key] = list(set(steps))
                else:
                    steps = [round(low + (high - low) * i / 4, 4) for i in range(5)]
                    param_grid[key] = steps
            else:
                param_grid[key] = [val]

        # Since we don't have a real evaluate_fn, return recommendation-only result
        result = OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="grid_search",
            best_params=current_params,
            recommendations=[
                f"Parameter grid generated for {strategy_name}: {list(param_grid.keys())}",
                "Run full optimization with historical data to find optimal parameters.",
                "Current parameters retained as baseline.",
            ],
        )
        self._history.append(result)
        return result

    # ─── History ──────────────────────────────────────────────

    def get_history(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """Get optimization history."""
        results = self._history
        if strategy_name:
            results = [r for r in results if r.strategy_name == strategy_name]
        return [r.to_dict() for r in results[-20:]]

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _max_drawdown(equity_curve: np.ndarray) -> float:
        """Compute max drawdown percentage from an equity curve."""
        if len(equity_curve) < 2:
            return 0.0
        peak = np.maximum.accumulate(equity_curve)
        dd = (equity_curve - peak) / np.where(peak != 0, peak, 1)
        return round(float(np.min(dd)) * 100, 2)

    # ─── FUTURE-READY STUBS ──────────────────────────────────

    def bayesian_optimize(self, evaluate_fn, param_bounds: Dict, strategy_name: str = "") -> OptimizationResult:
        """FUTURE-READY: Bayesian optimization using Gaussian Processes."""
        return OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="bayesian",
            recommendations=["Bayesian optimization requires scikit-optimize. Not yet implemented."],
        )

    def genetic_optimize(self, evaluate_fn, param_bounds: Dict, strategy_name: str = "") -> OptimizationResult:
        """FUTURE-READY: Genetic algorithm optimization."""
        return OptimizationResult(
            optimization_id=str(uuid.uuid4())[:8],
            strategy_name=strategy_name,
            method="genetic",
            recommendations=["Genetic optimization requires DEAP library. Not yet implemented."],
        )


# Singleton
strategy_optimizer = StrategyOptimizer()
