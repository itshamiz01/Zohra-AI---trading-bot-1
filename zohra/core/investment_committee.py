"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — MULTI-AGENT INVESTMENT COMMITTEE              ║
║        Consensus Debate, Risk Resolution, and Explainability         ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import logging
import requests
import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

logger = logging.getLogger("zohra.committee")

class BullAgent:
    """
    The Bull Agent:
    - Finds reasons to enter/justify trades in the proposed direction.
    - Evaluates bullish structure shifts, displacement, accumulation, and SMC confluences.
    """
    def generate_thesis(self, symbol: str, direction: str, setup_data: dict, scores: dict) -> Tuple[str, float]:
        reasons = []
        
        # Structure
        struct_score = scores.get("structure", 0)
        if struct_score >= 20:
            reasons.append("Strong market structure alignment with HH/HL pivots.")
        elif struct_score >= 10:
            reasons.append("Acceptable market structure bases forming.")
            
        # Liquidity
        liq_score = scores.get("liquidity", 0)
        if liq_score >= 15:
            reasons.append("Key liquidity pools swept, clearing path for acceleration.")
            
        # SMC / OB
        smc_score = scores.get("smc", 0)
        if smc_score >= 15:
            reasons.append("Price is testing a high-discount Order Block / FVG zone.")
            
        # Trend / Momentum
        trend_score = scores.get("trend", 0)
        if trend_score >= 10:
            reasons.append("EMA Trend alignment on multiple timeframes.")
            
        # Fallback if no strong reasons
        if not reasons:
            reasons.append("Standard trend pullback alignment.")

        thesis = (
            f"BULL THESIS ({direction}): Strong setup alignment on {symbol}. "
            f"Key drivers: {', '.join(reasons)} "
            f"SMC validation score: {smc_score}/20, Structure score: {struct_score}/25."
        )
        # Calculate confidence from the target direction
        confidence = float(scores.get("total", 0))
        return thesis, confidence

class BearAgent:
    """
    The Bear Agent:
    - Acts as the Critic / Devil's Advocate.
    - Challenges the trade, searches for traps, resistance, and failure probabilities.
    """
    def generate_thesis(self, symbol: str, direction: str, setup_data: dict, scores: dict) -> Tuple[str, float]:
        warnings = []
        
        # Volatility & Spread checks
        vol_score = scores.get("volatility", 0)
        if vol_score <= 2:
            warnings.append("Low volatility regime might trap capital in consolidation.")
            
        # Pullback checks
        pull_score = scores.get("pullback", 0)
        if pull_score <= 2:
            warnings.append("Price is extended far from the EMA mean (high reversion risk).")
            
        # Trend alignment risk
        trend_score = scores.get("trend", 0)
        if trend_score <= 5:
            warnings.append("Counter-trend execution carries higher failure probability.")
            
        # News calendar check
        if setup_data.get("is_news_blackout"):
            warnings.append("High-impact economic news window is active (high slippage risk).")
            
        if not warnings:
            warnings.append("General correlation risk and structural execution slippage.")

        risk_score = 100.0 - float(scores.get("total", 0))
        # High risk score = Bear agent is very worried
        thesis = (
            f"BEAR CRITIQUE: Challenging {direction} layout on {symbol}. "
            f"Warning factors: {', '.join(warnings)} "
            f"Failure probability estimated at {risk_score:.1f}% based on counter-metrics."
        )
        return thesis, risk_score

class RiskChairmanAgent:
    """
    The Risk Chairman Agent:
    - Resolves conflict between Bull and Bear agents.
    - Adjusts risk exposure based on drawdown.
    - Sets final trade grade (A+, A, B, C, Reject).
    """
    def evaluate_debate(self, symbol: str, direction: str, bull_thesis: str, bull_score: float, 
                        bear_thesis: str, bear_score: float, drawdown_pct: float, base_score: int) -> dict:
        
        # Core Chairman mediation logic
        final_score = int(base_score)
        
        from zohra.config.settings import ALLOW_C_SETUPS

        # Decide trade grade
        if final_score >= 90:
            grade = "A+"
            action = "EXECUTE"
            position_mult = 1.00
        elif final_score >= 80:
            grade = "A"
            action = "EXECUTE"
            position_mult = 0.75
        elif final_score >= 70:
            grade = "B"
            action = "EXECUTE"
            position_mult = 0.50
        elif final_score >= 60 and ALLOW_C_SETUPS:
            grade = "C"
            action = "EXECUTE"
            position_mult = 0.25
        else:
            grade = "REJECT"
            action = "REJECT"
            position_mult = 0.00

        # Drawdown adjustment
        dd_mult = 1.0
        if drawdown_pct >= 8.0:
            dd_mult = 0.0
            action = "REJECT"
        elif drawdown_pct >= 6.0:
            dd_mult = 0.25
        elif drawdown_pct >= 4.0:
            dd_mult = 0.50
        elif drawdown_pct >= 2.0:
            dd_mult = 0.75

        adjusted_mult = position_mult * dd_mult
        
        summary = (
            f"CHAIRMAN DECISION: {action} with grade {grade} (consensus score {final_score}/100). "
            f"Bull confidence={bull_score:.1f}%, Bear risk={bear_score:.1f}%. "
            f"Drawdown scaling adjusted sizing factor to {adjusted_mult:.2f}."
        )

        return {
            "approved": action in ("EXECUTE", "OPTIONAL") and final_score >= 70,
            "final_score": final_score,
            "grade": grade,
            "position_mult": adjusted_mult,
            "action": action,
            "chairman_summary": summary
        }

class InvestmentCommittee:
    """
    Orchestrator for the Investment Committee.
    Debates signals using either live LLM endpoints (Groq/OpenAI) or rule-based fallback.
    """
    def __init__(self):
        self.bull = BullAgent()
        self.bear = BearAgent()
        self.chairman = RiskChairmanAgent()
        
        # Check API configuration
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama3-70b-8192")

    def debate_setup(self, symbol: str, direction: str, strategy: str, 
                     setup_data: dict, drawdown_pct: float) -> dict:
        """
        Main debate loop. Returns structured decision dict.
        """
        scores = setup_data.get("scores_breakdown", {})
        base_score = setup_data.get("confidence_score", 0)
        if not scores and "score_structure" in setup_data:
            # Map database keys if needed
            scores = {
                "structure": setup_data.get("score_structure", 0),
                "liquidity": setup_data.get("score_liquidity", 0),
                "smc": setup_data.get("score_smc", 0),
                "trend": setup_data.get("score_trend", 0),
                "momentum": setup_data.get("score_momentum", 0),
                "volatility": setup_data.get("score_volatility", 0),
                "pullback": setup_data.get("score_pullback", 0),
                "total": base_score
            }
        else:
            scores["total"] = base_score

        # 1. Generate local rule-based theses (always acts as fallback / log feed)
        bull_thesis, bull_score = self.bull.generate_thesis(symbol, direction, setup_data, scores)
        bear_thesis, bear_score = self.bear.generate_thesis(symbol, direction, setup_data, scores)
        
        # 2. Try LLM debate if Groq API is active
        if self.groq_key:
            try:
                llm_debate = self._run_llm_debate(symbol, direction, strategy, scores, setup_data, drawdown_pct)
                if llm_debate:
                    return self._enrich_with_hie(symbol, direction, strategy, setup_data, llm_debate)
            except Exception as e:
                logger.error(f"Investment Committee LLM debate failed: {e}. Falling back to rule-based engine.")

        # 3. Fallback to rule-based evaluation
        decision = self.chairman.evaluate_debate(
            symbol=symbol,
            direction=direction,
            bull_thesis=bull_thesis,
            bull_score=bull_score,
            bear_thesis=bear_thesis,
            bear_score=bear_score,
            drawdown_pct=drawdown_pct,
            base_score=base_score
        )

        result = {
            "approved": decision["approved"],
            "final_score": decision["final_score"],
            "grade": decision["grade"],
            "position_mult": decision["position_mult"],
            "action": decision["action"],
            "bull_thesis": bull_thesis,
            "bear_thesis": bear_thesis,
            "chairman_summary": decision["chairman_summary"],
            "debate_log": [
                {"agent": "BullAgent", "text": bull_thesis, "score": bull_score},
                {"agent": "BearAgent", "text": bear_thesis, "score": bear_score},
                {"agent": "RiskChairman", "text": decision["chairman_summary"], "score": decision["final_score"]}
            ]
        }
        return self._enrich_with_hie(symbol, direction, strategy, setup_data, result)

    def _enrich_with_hie(self, symbol: str, direction: str, strategy: str, setup_data: dict, result: dict) -> dict:
        try:
            from zohra.hie.historical_intelligence_scoring import historical_intelligence_scoring
            
            session = setup_data.get("session", "London")
            technical_score = result.get("final_score", setup_data.get("confidence_score", 50.0))
            
            setup_type = setup_data.get("setup_type")
            if not setup_type:
                setup_type_map = {
                    "zohra_v5": "BOS",
                    "scalp_m5": "MomentumBreakout",
                    "mean_reversion": "TrendPullback",
                    "trend_following": "EMACross",
                    "breakout": "Breakout",
                    "momentumscalp": "MomentumBreakout"
                }
                setup_type = setup_type_map.get(strategy.lower(), None)
                
            timeframe = setup_data.get("timeframe", "H1")
            regime = setup_data.get("market_regime", "Trending")
            
            hie_result = historical_intelligence_scoring.enrich_score(
                symbol=symbol,
                direction=direction,
                session=session,
                technical_score=technical_score,
                setup_type=setup_type,
                timeframe=timeframe,
                regime=regime
            )
            
            result["historical_score"] = hie_result.get("historical_score")
            result["symbol_intelligence_score"] = hie_result.get("symbol_intel_score")
            result["market_memory_score"] = hie_result.get("market_memory_score")
            result["historical_matches"] = hie_result.get("historical_matches")
            result["historical_win_rate"] = hie_result.get("historical_win_rate")
            result["historical_avg_rr"] = hie_result.get("historical_avg_rr")
            result["historical_confidence"] = hie_result.get("historical_confidence")
            result["best_session"] = hie_result.get("best_session")
            
            if hie_result.get("data_available"):
                blended_score = hie_result.get("blended_score")
                result["final_score"] = blended_score
                result["grade"] = hie_result.get("grade")
                
                if blended_score < 70:
                    result["approved"] = False
                    result["action"] = "REJECT"
                    result["position_mult"] = 0.0
            
            logger.info(historical_intelligence_scoring.format_hie_log(symbol, direction, hie_result))
            
        except Exception as e:
            logger.error(f"Failed to enrich debate result with HIE: {e}")
            
        return result


    def _run_llm_debate(self, symbol: str, direction: str, strategy: str, 
                         scores: dict, setup_data: dict, drawdown_pct: float) -> Optional[dict]:
        """
        Executes a multi-agent structured debate via Groq API.
        """
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        
        prompt = (
            f"You are the Investment Committee for the institutional Zohra AI Trading Engine.\n"
            f"Trade Proposal:\n"
            f"- Asset: {symbol}\n"
            f"- Direction: {direction}\n"
            f"- Strategy: {strategy}\n"
            f"- Current Account Drawdown: {drawdown_pct:.2f}%\n"
            f"- Tech Scores: Structure {scores.get('structure')}/25, Liquidity {scores.get('liquidity')}/20, "
            f"SMC {scores.get('smc')}/20, Trend {scores.get('trend')}/15, Momentum {scores.get('momentum')}/10, "
            f"Volatility {scores.get('volatility')}/5, Pullback {scores.get('pullback')}/5.\n"
            f"- Base Score: {scores.get('total')}/100\n\n"
            f"Write a debate transcript with three sections:\n"
            f"1. BULL THESIS: Outline entry arguments (BOS/CHoCH, liquidity grabs, accumulation).\n"
            f"2. BEAR CRITIQUE: Outline warning flags (exhaustion, resistance zones, low volatility, news risk).\n"
            f"3. CHAIRMAN RULING: Resolve debate, state final decision (APPROVE/REJECT), final consensus score (0-100), "
            f"and grade (A+=90-100, A=80-89, B=70-79, C=60-69, Reject=Below 60). No trade under 70 can execute.\n\n"
            f"Output must be strictly valid JSON matching this format:\n"
            f'{{"bull_thesis": "...", "bear_thesis": "...", "approved": true/false, "final_score": 85, "grade": "A", "chairman_summary": "..."}}'
        )

        resp = requests.post(
            url,
            headers=headers,
            json={
                "model": self.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"}
            },
            timeout=10
        )
        
        if resp.status_code == 200:
            res_json = resp.json()
            content = res_json["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            
            # Chairman drawdown sizing logic adjustment
            position_mult = 1.0
            g = parsed.get("grade", "B")
            if g == "A+": position_mult = 1.00
            elif g == "A": position_mult = 0.75
            elif g == "B": position_mult = 0.50
            elif g == "C": position_mult = 0.25
            else: position_mult = 0.00

            dd_mult = 1.0
            if drawdown_pct >= 8.0: dd_mult = 0.0
            elif drawdown_pct >= 6.0: dd_mult = 0.25
            elif drawdown_pct >= 4.0: dd_mult = 0.50
            elif drawdown_pct >= 2.0: dd_mult = 0.75
            
            parsed["position_mult"] = position_mult * dd_mult
            
            # Enforce hard safety rules
            if parsed["final_score"] < 70:
                parsed["approved"] = False
                parsed["position_mult"] = 0.0
                
            parsed["action"] = "EXECUTE" if parsed["approved"] else "REJECT"
            parsed["debate_log"] = [
                {"agent": "BullAgent", "text": parsed["bull_thesis"], "score": scores.get('total')},
                {"agent": "BearAgent", "text": parsed["bear_thesis"], "score": 100 - scores.get('total')},
                {"agent": "RiskChairman", "text": parsed["chairman_summary"], "score": parsed["final_score"]}
            ]
            return parsed
        return None

# Singleton
investment_committee = InvestmentCommittee()
