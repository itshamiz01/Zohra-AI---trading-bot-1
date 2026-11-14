"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 9 — HISTORICAL INTELLIGENCE SCORING (COLD-START ADAPTIVE)   ║
║   Blends historical data with technical score dynamically.           ║
║   In cold-start mode, redistributes missing weights proportionally.   ║
║   NEVER penalizes valid technical setups with missing data.          ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from typing import Dict, Optional, Any, Tuple

logger = logging.getLogger("zohra.hie.scoring")

# Baseline mature-data score weights (must sum to 1.0)
SCORE_WEIGHTS = {
    "technical":    0.40,
    "historical":   0.30,
    "symbol_intel": 0.15,
    "memory":       0.15,
}

# Minimum reliable sample sizes required to activate historical modules
MIN_SAMPLE_SIZES = {
    "historical":   5,  # Need >= 5 historical pattern matches
    "symbol_intel": 5,  # Need >= 5 symbol-specific trades
    "memory":       3,  # Need >= 3 vector memory matches
}


def _grade_from_score(score: float) -> str:
    if score >= 90:
        return "A+"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 60:
        return "C"
    else:
        return "REJECT"


class HistoricalIntelligenceScoring:
    """
    Adaptive Multi-Layer Trade Quality & Expectancy Scorer.
    
    MATURE DATA MODE: Uses full 40/30/15/15 weighting when historical databases have sufficient sample size.
    COLD START MODE: When historical/memory data is unavailable, temporarily removes its weight and
    redistributes it proportionally across validated available components (e.g. 100% technical score).
    """

    def __init__(self):
        self.base_weights = dict(SCORE_WEIGHTS)

    def enrich_score(
        self,
        symbol: str,
        direction: str,
        session: str,
        technical_score: float,
        setup_type: Optional[str] = None,
        timeframe: Optional[str] = None,
        regime: Optional[str] = None,
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        spread_pips: float = 2.0
    ) -> Dict[str, Any]:
        """
        Compute cold-start adaptive blended score with transparent component telemetry and Expectancy (EV).
        """
        try:
            # 1. Inspect data availability & sample sizes
            hist_score, hist_samples, hist_avail, hist_rel, similarity = self._evaluate_historical_source(
                symbol, direction, session, setup_type
            )
            sym_score, sym_samples, sym_avail, sym_rel = self._evaluate_symbol_source(
                symbol, session, setup_type, direction
            )
            mem_score, mem_samples, mem_avail, mem_rel = self._evaluate_memory_source(
                symbol, session, setup_type, direction
            )

            # 2. Build component status dictionary
            components = {
                "technical": {
                    "value": round(float(technical_score), 2),
                    "base_weight": self.base_weights["technical"],
                    "data_available": True,
                    "sample_size": 100,
                    "reliability": 1.0,
                },
                "historical": {
                    "value": round(float(hist_score), 2),
                    "base_weight": self.base_weights["historical"],
                    "data_available": hist_avail,
                    "sample_size": hist_samples,
                    "reliability": hist_rel,
                },
                "symbol_intel": {
                    "value": round(float(sym_score), 2),
                    "base_weight": self.base_weights["symbol_intel"],
                    "data_available": sym_avail,
                    "sample_size": sym_samples,
                    "reliability": sym_rel,
                },
                "memory": {
                    "value": round(float(mem_score), 2),
                    "base_weight": self.base_weights["memory"],
                    "data_available": mem_avail,
                    "sample_size": mem_samples,
                    "reliability": mem_rel,
                }
            }

            # 3. Dynamic Cold-Start Weight Redistribution
            active_base_sum = sum(comp["base_weight"] for comp in components.values() if comp["data_available"])
            is_mature = all(comp["data_available"] for comp in components.values())
            mode = "MATURE_DATA" if is_mature else "COLD_START_ADAPTIVE"

            blended_sum = 0.0
            for name, comp in components.items():
                if comp["data_available"] and active_base_sum > 0:
                    normalized_weight = comp["base_weight"] / active_base_sum
                else:
                    normalized_weight = 0.0

                comp["active_weight"] = round(normalized_weight, 4)
                comp["contribution"] = round(comp["value"] * normalized_weight, 2)
                blended_sum += comp["contribution"]

            final_blended_score = max(0.0, min(100.0, round(blended_sum, 2)))
            grade = _grade_from_score(final_blended_score)

            # 4. Multi-Layer Expectancy (EV) Calculation
            ev_metrics = self._calculate_expectancy(
                final_score=final_blended_score,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                spread_pips=spread_pips,
                similarity=similarity
            )

            # 5. Recommendation & Logging
            recommendation = self._get_recommendation(grade, final_blended_score, similarity, mode)

            result = {
                "technical_score":     round(technical_score, 2),
                "historical_score":    round(hist_score, 2),
                "symbol_intel_score":  round(sym_score, 2),
                "market_memory_score": round(mem_score, 2),
                "blended_score":       final_blended_score,
                "grade":               grade,
                "scoring_mode":        mode,
                "components":          components,
                "expectancy_metrics":  ev_metrics,
                "historical_matches":  similarity.get("match_count", 0),
                "historical_win_rate": similarity.get("win_rate", 0),
                "historical_avg_rr":   similarity.get("avg_rr", 0),
                "historical_confidence": similarity.get("confidence", "COLD_START"),
                "best_session":        similarity.get("best_session", session),
                "weights_used":        {k: v["active_weight"] for k, v in components.items()},
                "data_available":      is_mature,
                "recommendation":      recommendation
            }

            logger.info(self.format_hie_log(symbol, direction, result))
            return result

        except Exception as e:
            logger.error(f"HIE score enrichment error: {e}")
            grade = _grade_from_score(technical_score)
            return {
                "technical_score":     round(technical_score, 2),
                "historical_score":    round(technical_score, 2),
                "symbol_intel_score":  round(technical_score, 2),
                "market_memory_score": round(technical_score, 2),
                "blended_score":       round(technical_score, 2),
                "grade":               grade,
                "scoring_mode":        "ERROR_FALLBACK_TECHNICAL_ONLY",
                "components":          {},
                "expectancy_metrics":  {},
                "historical_matches":  0,
                "historical_win_rate": 0,
                "historical_avg_rr":   0,
                "historical_confidence": "INSUFFICIENT DATA",
                "best_session":        session,
                "weights_used":        {"technical": 1.0, "historical": 0.0, "symbol_intel": 0.0, "memory": 0.0},
                "data_available":      False,
                "recommendation":      "Technical analysis only — HIE data loading."
            }

    def _evaluate_historical_source(self, symbol: str, direction: str, session: str, setup_type: Optional[str]) -> Tuple[float, int, bool, float, Dict]:
        """Evaluates historical trade pattern database."""
        try:
            from zohra.hie.trade_similarity_engine import trade_similarity_engine
            sim = trade_similarity_engine.find_similar(symbol, direction, session, setup_type)
            matches = sim.get("match_count", 0)
            conf = sim.get("confidence", "INSUFFICIENT DATA")

            if matches >= MIN_SAMPLE_SIZES["historical"] and conf in ("HIGH", "MEDIUM"):
                score = float(trade_similarity_engine.get_similarity_score(symbol, direction, session, setup_type))
                rel = 1.0 if conf == "HIGH" else 0.8
                return score, matches, True, rel, sim
            return 0.0, matches, False, 0.0, sim
        except Exception:
            return 0.0, 0, False, 0.0, {"match_count": 0, "win_rate": 0, "avg_rr": 0, "confidence": "N/A", "best_session": session}

    def _evaluate_symbol_source(self, symbol: str, session: str, setup_type: Optional[str], direction: str) -> Tuple[float, int, bool, float]:
        """Evaluates symbol-specific performance profile."""
        try:
            from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
            profile = symbol_intelligence_profiles.get_profile(symbol) if hasattr(symbol_intelligence_profiles, "get_profile") else None
            trade_count = getattr(profile, "total_trades", 0) if profile else 0

            if trade_count >= MIN_SAMPLE_SIZES["symbol_intel"]:
                score = float(symbol_intelligence_profiles.get_symbol_score(symbol, session, setup_type or "", direction))
                return score, trade_count, True, 0.9
            return 0.0, trade_count, False, 0.0
        except Exception:
            return 0.0, 0, False, 0.0

    def _evaluate_memory_source(self, symbol: str, session: str, setup_type: Optional[str], direction: str) -> Tuple[float, int, bool, float]:
        """Evaluates vector market memory engine."""
        try:
            from zohra.hie.market_memory_engine import market_memory_engine
            matches = market_memory_engine.get_match_count(symbol) if hasattr(market_memory_engine, "get_match_count") else 0

            if matches >= MIN_SAMPLE_SIZES["memory"]:
                score = float(market_memory_engine.get_memory_score(symbol, session, setup_type or "", direction))
                return score, matches, True, 0.85
            return 0.0, matches, False, 0.0
        except Exception:
            return 0.0, 0, False, 0.0

    def _calculate_expectancy(self, final_score: float, entry_price: float,
                              stop_loss: float, take_profit: float,
                              spread_pips: float, similarity: Dict) -> Dict[str, Any]:
        """
        Calculates mathematical Expected Value (EV) per trade:
        EV = (Win_Prob * Avg_Win) - (Loss_Prob * Avg_Loss) - Tx_Costs
        """
        # 1. Estimate Win Probability from calibrated score + historical win rate
        hist_wr = similarity.get("win_rate", 0.0) / 100.0
        if hist_wr > 0 and similarity.get("match_count", 0) >= 5:
            win_prob = (0.5 * (final_score / 100.0)) + (0.5 * hist_wr)
        else:
            win_prob = final_score / 100.0

        loss_prob = 1.0 - win_prob

        # 2. Risk / Reward distances
        if entry_price > 0 and stop_loss > 0 and take_profit > 0:
            avg_win_dist = abs(take_profit - entry_price)
            avg_loss_dist = abs(entry_price - stop_loss)
            tx_cost = (spread_pips * 0.10)  # Spread cost in USD on Gold
        else:
            avg_win_dist = 2.0
            avg_loss_dist = 1.0
            tx_cost = 0.30

        # 3. Expected Value
        expected_value = (win_prob * avg_win_dist) - (loss_prob * avg_loss_dist) - tx_cost
        is_positive_expectancy = expected_value > 0.0

        return {
            "win_probability": round(win_prob, 3),
            "loss_probability": round(loss_prob, 3),
            "avg_win_usd": round(avg_win_dist, 2),
            "avg_loss_usd": round(avg_loss_dist, 2),
            "tx_cost_usd": round(tx_cost, 2),
            "expected_value_usd": round(expected_value, 2),
            "has_positive_expectancy": is_positive_expectancy
        }

    def _get_recommendation(self, grade: str, score: float, similarity: Dict, mode: str) -> str:
        n = similarity.get("match_count", 0)
        wr = similarity.get("win_rate", 0)
        avg_rr = similarity.get("avg_rr", 0)

        if mode == "COLD_START_ADAPTIVE":
            if grade in ("A+", "A", "B"):
                return f"✅ APPROVED (Cold-Start Adaptive) — Technical Score: {score:.0f}/100. Weight redistributed to live validated components."
            else:
                return f"⛔ REJECTED — Technical setup quality ({score:.0f}/100) below minimum execution threshold."

        if grade in ("A+", "A") and similarity.get("confidence") == "HIGH":
            return f"✅ STRONGLY APPROVED — {n} historical matches, {wr:.1f}% WR, {avg_rr:.1f}R avg"
        elif grade == "REJECT":
            return f"⛔ REJECTED — Multi-layer score ({score:.0f}/100) below threshold."
        else:
            return f"📊 APPROVED — Score {score:.0f} | {n} matches | {wr:.1f}% WR"

    def format_hie_log(self, symbol: str, direction: str, result: Dict) -> str:
        """Format HIE score result for terminal logging."""
        mode_tag = "COLD-START" if result.get("scoring_mode") == "COLD_START_ADAPTIVE" else "MATURE"
        weights_str = ", ".join(f"{k}:{v*100:.0f}%" for k, v in result.get("weights_used", {}).items())
        ev_data = result.get("expectancy_metrics", {})
        ev_str = f"EV=+${ev_data.get('expected_value_usd', 0.0):.2f}" if ev_data.get('has_positive_expectancy') else f"EV=-${abs(ev_data.get('expected_value_usd', 0.0)):.2f}"

        return (
            f"📊 HIE ADAPTIVE [{mode_tag}]: {symbol} {direction} | "
            f"Tech: {result['technical_score']:.0f} | "
            f"Hist: {result['historical_score']:.0f} | "
            f"Sym: {result['symbol_intel_score']:.0f} | "
            f"Mem: {result['market_memory_score']:.0f} | "
            f"FINAL SCORE: {result['blended_score']:.0f} [GRADE: {result['grade']}] | "
            f"Weights: [{weights_str}] | {ev_str}"
        )


# Master singleton instance
historical_intelligence_scoring = HistoricalIntelligenceScoring()
