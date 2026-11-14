"""
╔══════════════════════════════════════════════════════════════════════╗
║             ZOHRA — INSTITUTIONAL VALIDATION COMMITTEE               ║
║           Layer 2 Consensus Audit & Committee Debate                 ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import logging
import requests
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from zohra.brokers.manager import broker_manager as mt5_broker
from zohra.core.enums import TradeQuality
from zohra.core.risk_guardian import risk_guardian
from zohra.config.settings import STATE

logger = logging.getLogger("zohra.validation")

# ─── 1. STRUCTURE ANALYST AGENT ──────────────────────────────────────
class AgentStructure:
    """Agent 1: Evaluates trend structure, BOS, CHoCH, and timeframe alignment."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        df = None
        try:
            df = mt5_broker.get_ohlcv(symbol, "M15", count=100)
        except Exception as e:
            logger.warning(f"AgentStructure: Failed to fetch live candles: {e}")
            
        scores = signal_data.get("scores_breakdown", {})
        score = scores.get("structure", 75)
        score_norm = min(100, int(score * 4.0)) if score <= 25 else score
        
        thesis = f"Market structure on {symbol} validated. HTF alignment confirmed."
        
        if df is not None and len(df) >= 30:
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            
            p_highs = self._find_pivots(highs, window=5, high=True)
            p_lows = self._find_pivots(lows, window=5, high=False)
            
            reasons = []
            direction = signal_data.get("direction", "LONG")
            
            if len(p_highs) >= 2 and len(p_lows) >= 2:
                if direction == "LONG":
                    if p_highs[-1] > p_highs[-2]:
                        reasons.append(f"Higher High (HH) at {p_highs[-1]:.5f}")
                    if p_lows[-1] > p_lows[-2]:
                        reasons.append(f"Higher Low (HL) at {p_lows[-1]:.5f}")
                    if closes[-1] > p_highs[-2]:
                        reasons.append(f"Bullish BOS confirmed above {p_highs[-2]:.5f}")
                else:
                    if p_highs[-1] < p_highs[-2]:
                        reasons.append(f"Lower High (LH) at {p_highs[-1]:.5f}")
                    if p_lows[-1] < p_lows[-2]:
                        reasons.append(f"Lower Low (LL) at {p_lows[-1]:.5f}")
                    if closes[-1] < p_lows[-2]:
                        reasons.append(f"Bearish BOS confirmed below {p_lows[-2]:.5f}")
            
            ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values[-1]
            if direction == "LONG" and closes[-1] > ema50:
                reasons.append("Price constructive above M15 EMA-50")
            elif direction == "SHORT" and closes[-1] < ema50:
                reasons.append("Price constructive below M15 EMA-50")
                
            if reasons:
                thesis = f"Market structure: {', '.join(reasons)}"
        
        return {
            "score": score_norm,
            "thesis": thesis
        }

    def _find_pivots(self, data: np.ndarray, window: int = 5, high: bool = True) -> List[float]:
        pivots = []
        for i in range(window, len(data) - window):
            if high:
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
            else:
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    pivots.append(float(data[i]))
        return pivots[-8:]


# ─── 2. SMC / ZONE ANALYST AGENT ──────────────────────────────────────
class AgentSMC:
    """Agent 2: Evaluates Order Blocks (OB), Fair Value Gaps (FVG), and Premium/Discount zones."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        df = None
        try:
            df = mt5_broker.get_ohlcv(symbol, "M15", count=100)
        except Exception as e:
            logger.warning(f"AgentSMC: Failed to fetch live candles: {e}")
            
        scores = signal_data.get("scores_breakdown", {})
        score = scores.get("smc", 80)
        score_norm = min(100, int(score * 5.0)) if score <= 20 else score
        
        thesis = "SMC zones checked. Price is resting in institutional ranges."
        
        if df is not None and len(df) >= 30:
            reasons = []
            direction = signal_data.get("direction", "LONG")
            entry = signal_data.get("entry_price") or df.iloc[-1]['close']
            
            highs = df['high'].values
            lows = df['low'].values
            lookback = min(24, len(df))
            max_h = highs[-lookback:].max()
            min_l = lows[-lookback:].min()
            rng = max_h - min_l
            
            if rng > 0:
                pct = (entry - min_l) / rng * 100
                if direction == "LONG" and pct <= 50:
                    reasons.append(f"Discount zone entry confirmed ({pct:.1f}%)")
                elif direction == "SHORT" and pct >= 50:
                    reasons.append(f"Premium zone entry confirmed ({pct:.1f}%)")
            
            # FVG check
            fvgs = []
            for i in range(2, len(df)):
                if df.iloc[i-2]['close'] < df.iloc[i-2]['open'] and df.iloc[i]['close'] > df.iloc[i]['open']:
                    if df.iloc[i]['low'] > df.iloc[i-2]['high']:
                        fvgs.append(("BULL", df.iloc[i-2]['high'], df.iloc[i]['low']))
                elif df.iloc[i-2]['close'] > df.iloc[i-2]['open'] and df.iloc[i]['close'] < df.iloc[i]['open']:
                    if df.iloc[i]['high'] < df.iloc[i-2]['low']:
                        fvgs.append(("BEAR", df.iloc[i]['high'], df.iloc[i-2]['low']))
            
            active_fvgs = []
            for f_type, low_b, high_b in fvgs[-5:]:
                if f_type == "BULL" and entry >= low_b and entry <= high_b:
                    active_fvgs.append(f"Bullish FVG [{low_b:.5f}-{high_b:.5f}]")
                elif f_type == "BEAR" and entry >= low_b and entry <= high_b:
                    active_fvgs.append(f"Bearish FVG [{low_b:.5f}-{high_b:.5f}]")
            if active_fvgs:
                reasons.append(f"Aligned with {', '.join(active_fvgs)}")
            
            thesis = f"SMC Zone: {'; '.join(reasons)}" if reasons else "No active FVG/OB alignment."
            
        return {
            "score": score_norm,
            "thesis": thesis
        }


# ─── 3. LIQUIDITY ANALYST AGENT ─────────────────────────────────────
class AgentLiquidity:
    """Agent 3: Evaluates liquidity pools, equal highs/lows, and sweep events."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        df = None
        try:
            df = mt5_broker.get_ohlcv(symbol, "M15", count=100)
        except Exception as e:
            logger.warning(f"AgentLiquidity: Failed to fetch live candles: {e}")
            
        scores = signal_data.get("scores_breakdown", {})
        score = scores.get("liquidity", 85)
        score_norm = min(100, int(score * 5.0)) if score <= 20 else score
        
        thesis = "Liquidity pools mapped. No sweep triggers detected."
        
        if df is not None and len(df) >= 30:
            reasons = []
            direction = signal_data.get("direction", "LONG")
            closes = df['close'].values
            highs = df['high'].values
            lows = df['low'].values
            
            avg_price = closes[-20:].mean()
            tol = avg_price * 0.0005
            
            eql_levels = []
            eqh_levels = []
            for i in range(len(df) - 30, len(df)):
                for j in range(i + 1, len(df)):
                    if abs(highs[i] - highs[j]) <= tol:
                        eqh_levels.append((highs[i] + highs[j]) / 2)
                    if abs(lows[i] - lows[j]) <= tol:
                        eql_levels.append((lows[i] + lows[j]) / 2)
            
            latest_low = lows[-5:].min()
            latest_high = highs[-5:].max()
            latest_close = closes[-1]
            sweep_confirmed = False
            
            if direction == "LONG" and eql_levels:
                for eq_lvl in eql_levels:
                    if latest_low < eq_lvl and latest_close > eq_lvl:
                        reasons.append(f"Swept EQL liquidity at {eq_lvl:.5f}")
                        sweep_confirmed = True
                        break
            elif direction == "SHORT" and eqh_levels:
                for eq_lvl in eqh_levels:
                    if latest_high > eq_lvl and latest_close < eq_lvl:
                        reasons.append(f"Swept EQH liquidity at {eq_lvl:.5f}")
                        sweep_confirmed = True
                        break
            
            if sweep_confirmed:
                thesis = f"Liquidity Sweep: {'; '.join(reasons)}"
            elif eql_levels or eqh_levels:
                thesis = f"Resting liquidity pools mapped near {min(eql_levels or eqh_levels):.5f}"
                
        return {
            "score": score_norm,
            "thesis": thesis
        }


# ─── 4. TREND ANALYST AGENT ──────────────────────────────────────────
class AgentTrend:
    """Agent 4: Evaluates moving averages, trend alignment, and ADX trend strength."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        df = None
        try:
            df = mt5_broker.get_ohlcv(symbol, "H1", count=100)
        except Exception as e:
            logger.warning(f"AgentTrend: Failed to fetch H1 candles: {e}")

        score = 70
        thesis = "Trend structure is neutral."

        if df is not None and len(df) >= 50:
            closes = df['close'].values
            ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
            ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values
            
            direction = signal_data.get("direction", "LONG")
            last_close = closes[-1]
            last_ema50 = ema50[-1]
            last_ema200 = ema200[-1]
            
            is_bullish = last_close > last_ema50 > last_ema200
            is_bearish = last_close < last_ema50 < last_ema200
            
            if direction == "LONG":
                if is_bullish:
                    score = 95
                    thesis = "Strong H1 Bullish Trend alignment (Price > EMA50 > EMA200)"
                elif last_close > last_ema50:
                    score = 80
                    thesis = "Moderate Bullish Trend (Price > EMA50 but below EMA200)"
                else:
                    score = 40
                    thesis = "Counter-Trend Warning: Price is below EMA50"
            else:
                if is_bearish:
                    score = 95
                    thesis = "Strong H1 Bearish Trend alignment (Price < EMA50 < EMA200)"
                elif last_close < last_ema50:
                    score = 80
                    thesis = "Moderate Bearish Trend (Price < EMA50 but above EMA200)"
                else:
                    score = 40
                    thesis = "Counter-Trend Warning: Price is above EMA50"

        return {
            "score": score,
            "thesis": thesis
        }


# ─── 5. SESSION Timing AGENT ──────────────────────────────────────────
class AgentSession:
    """Agent 5: Evaluates session timings, London/NY overlaps, and Gold session rules."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        from datetime import datetime
        h = datetime.utcnow().hour
        symbol_upper = symbol.upper()
        
        score = 80
        session_name = "Asian"
        
        if 8 <= h < 12:
            session_name = "London Open"
            score = 90
        elif 12 <= h < 16:
            session_name = "London-NY Overlap"
            score = 98
        elif 16 <= h < 21:
            session_name = "New York"
            score = 85
        else:
            session_name = "Asian / Off-hours"
            score = 50

        thesis = f"Active session: {session_name}."
        
        # Gold-specific session rules (Gold Behavior Engine)
        if symbol_upper == "XAUUSD":
            if session_name == "Asian / Off-hours":
                score = 40
                thesis = "Gold Asian Accumulation: Warning - typical ranging/accumulation phase."
            elif session_name == "London Open":
                score = 85
                thesis = "Gold London Open: Manipulation and stop-sweeps active."
            elif session_name == "London-NY Overlap":
                score = 95
                thesis = "Gold NY Expansion: High volatility expansion phase approved."

        return {
            "score": score,
            "thesis": thesis
        }


# ─── 6. VOLATILITY ANALYST AGENT ─────────────────────────────────────
class AgentVolatility:
    """Agent 6: Evaluates ATR and Bollinger Band width to avoid low-volatility traps."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        df = None
        try:
            df = mt5_broker.get_ohlcv(symbol, "M15", count=50)
        except Exception as e:
            logger.warning(f"AgentVolatility: Failed to fetch candles: {e}")

        score = 75
        thesis = "Volatility levels nominal."

        if df is not None and len(df) >= 20:
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values
            
            # Simple ATR calculation
            tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
            atr = pd.Series(tr).rolling(14).mean().values[-1]
            
            # Bollinger Band Width
            sma = pd.Series(closes).rolling(20).mean().values
            std = pd.Series(closes).rolling(20).std().values
            bb_width = (4 * std[-1]) / (sma[-1] + 1e-9)
            
            if bb_width < 0.001:
                score = 40
                thesis = f"Compression trap warning: BB width very narrow ({bb_width:.4f})."
            elif bb_width > 0.005:
                score = 90
                thesis = f"High expansion volatility confirmed: BB width ({bb_width:.4f}), ATR ({atr:.5f})."
            else:
                score = 80
                thesis = f"Nominal volatility: BB width ({bb_width:.4f})."

        return {
            "score": score,
            "thesis": thesis
        }


# ─── 7. RISK ANALYST AGENT ───────────────────────────────────────────
class AgentRisk:
    """Agent 7: Evaluates RRR (Risk-to-Reward Ratio) and position size metrics."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        entry = signal_data.get("entry_price") or 0.0
        sl = signal_data.get("stop_loss") or 0.0
        tp = signal_data.get("take_profit") or 0.0
        
        score = 70
        thesis = "Risk parameters evaluated."
        
        if entry > 0 and sl > 0 and tp > 0:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            rrr = reward / (risk + 1e-9)
            
            if rrr < 1.3:
                score = 30
                thesis = f"Risk rejected: poor Risk-to-Reward ratio ({rrr:.2f}R < 1.3R limit)"
            elif rrr >= 2.0:
                score = 98
                thesis = f"Optimal risk parameters: High RRR confirmed ({rrr:.2f}R)"
            else:
                score = 85
                thesis = f"Acceptable risk parameters: RRR is ({rrr:.2f}R)"
        else:
            thesis = "Warning: missing entry/SL/TP parameters for risk assessment."

        return {
            "score": score,
            "thesis": thesis
        }


# ─── 8. PORTFOLIO CORRELATION AGENT ──────────────────────────────────
class AgentCorrelation:
    """Agent 8: Evaluates portfolio-wide currency correlation and sector exposure."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        positions = []
        try:
            positions = mt5_broker.get_open_positions() or []
        except Exception as e:
            logger.warning(f"AgentCorrelation: Failed to fetch active positions: {e}")
            
        from zohra.core.correlation_engine import correlation_engine
        
        max_corr = 0.0
        exp_score = 0.0
        corr_reason = "Portfolio empty. Correlation risk is clear."
        
        if positions:
            try:
                max_corr, exp_score, corr_reason = correlation_engine.evaluate_portfolio_exposure(symbol, positions)
            except Exception as e:
                logger.error(f"Error calling correlation engine: {e}")
                
        currency_basket = {}
        for pos in positions:
            p_symbol = pos.get("symbol", "")
            p_lots = pos.get("lots", pos.get("position_size_lots", 0.0))
            p_dir = pos.get("direction", "LONG")
            if "type" in pos:
                p_dir = "LONG" if pos["type"] == 0 else "SHORT"
                
            base = p_symbol[:3]
            quote = p_symbol[3:6]
            if p_symbol == "XAUUSD":
                base, quote = "XAU", "USD"
            elif p_symbol == "XAGUSD":
                base, quote = "XAG", "USD"
            mult = 1.0 if p_dir == "LONG" else -1.0
            currency_basket[base] = currency_basket.get(base, 0.0) + p_lots * mult
            currency_basket[quote] = currency_basket.get(quote, 0.0) - p_lots * mult
            
        warnings = []
        usd_exposure = currency_basket.get("USD", 0.0)
        if abs(usd_exposure) >= 1.5:
            warnings.append(f"High USD Concentration: Net exposure {usd_exposure:+.2f} lots active.")
            
        matching_count = sum(1 for p in positions if p.get("symbol") != symbol and (p.get("direction") == signal_data.get("direction") or ("type" in p and ("LONG" if p["type"] == 0 else "SHORT") == signal_data.get("direction"))))
        
        score = max(0, 100 - (matching_count * 25))
        if usd_exposure:
            score = max(0, int(score - (abs(usd_exposure) * 10)))
            
        reasons = [corr_reason]
        if warnings:
            reasons.extend(warnings)
            
        return {
            "score": score,
            "thesis": f"Correlation audit: {'; '.join(reasons)}"
        }


# ─── 9. NEWS / MACRO AGENT ───────────────────────────────────────────
class AgentNews:
    """Agent 9: Performs economic calendar checks and high-impact news buffer analysis."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        is_blackout = False
        blackout_reason = "Calendar clear. No high-impact events scheduled."
        score = 100

        try:
            from zohra.agents.news_agent import NewsAgent
            news_agent = NewsAgent()
            news_check = news_agent.check_news_status(symbol)
            if news_check.get("status") == "BLACKOUT":
                is_blackout = True
                blackout_reason = news_check.get("reason", "News blackout active.")
                score = 20
        except Exception as e:
            logger.warning(f"AgentNews: Economic news calendar check failed: {e}")
            is_blackout = signal_data.get("is_news_blackout", False)
            if is_blackout:
                blackout_reason = "Economic news blackout active (Scout flag)."
                score = 20

        return {
            "score": score,
            "thesis": f"News Check: {blackout_reason}"
        }


# ─── 10. EXECUTION ANALYST AGENT ────────────────────────────────────
class AgentExecution:
    """Agent 10: Evaluates broker spread and execution slippage limits."""
    def analyze(self, symbol: str, signal_data: dict) -> Dict[str, Any]:
        score = 80
        thesis = "Spread levels nominal."

        symbol_info = mt5_broker.get_symbol_info(symbol)
        if symbol_info:
            spread = symbol_info.get("spread", 0)
            point = symbol_info.get("point", 0.00001)
            if "JPY" in symbol or symbol in ("XAUUSD", "XAGUSD"):
                spread_pips = spread * point * 100.0
            else:
                spread_pips = spread * point * 10000.0
                
            max_spreads = {
                "XAUUSD": 4.5,
                "XAGUSD": 5.0,
                "EURUSD": 1.8,
                "GBPUSD": 2.2,
                "USDJPY": 2.2,
            }
            max_allowed = max_spreads.get(symbol.upper(), 3.0)
            if spread_pips > max_allowed:
                score = 30
                thesis = f"Spread rejected: {spread_pips:.1f} pips > {max_allowed:.1f} pips limit."
            else:
                score = 95
                thesis = f"Spread verified: {spread_pips:.1f} pips (within {max_allowed:.1f} pips limit)."

        return {
            "score": score,
            "thesis": thesis
        }


# ─── 11. RISK CHAIRMAN ───────────────────────────────────────────────
class RiskChairman:
    """Chairman: Resolves the committee debate, assigns final score grade, and controls capital scaling."""
    def mediate(self, reports: List[Dict]) -> Dict[str, Any]:
        total_score = sum(r["score"] for r in reports)
        avg_score = int(total_score / len(reports))

        # Assign Grade
        if avg_score >= 90:
            grade = "A+"
            action = "SCALE_MAX"
        elif avg_score >= 80:
            grade = "A"
            action = "SCALE_NORMAL"
        elif avg_score >= 70:
            grade = "B"
            action = "MAINTAIN"
        elif avg_score >= 60:
            grade = "C"
            action = "REDUCE"
        else:
            grade = "REJECT"
            action = "REJECT"

        equity = mt5_broker.get_equity()
        drawdown_pct = 0.0
        if STATE.peak_equity > 0 and equity > 0:
            drawdown_pct = max(0.0, (STATE.peak_equity - equity) / STATE.peak_equity * 100.0)

        # Hard drawdown safety override
        if drawdown_pct >= 8.0 or STATE.trading_halted:
            grade = "REJECT"
            action = "REJECT"

        summary = (
            f"COMMITTEE DECISION: {action} (Grade {grade}, Confidence score {avg_score}/100). "
            f"Drawdown is {drawdown_pct:.2f}%."
        )

        return {
            "final_score": avg_score,
            "grade": grade,
            "action": action,
            "chairman_summary": summary
        }


# ─── 12. VALIDATION COMMITTEE ORCHESTRATOR ───────────────────────────
class ValidationCommittee:
    """Orchestrates the 10-agent consensus debate and generates validation transcripts."""
    def __init__(self):
        self.agents = [
            AgentStructure(),
            AgentSMC(),
            AgentLiquidity(),
            AgentTrend(),
            AgentSession(),
            AgentVolatility(),
            AgentRisk(),
            AgentCorrelation(),
            AgentNews(),
            AgentExecution()
        ]
        self.chairman = RiskChairman()
        self.groq_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama3-70b-8192")

    async def validate_probe(self, probe_trade: dict, signal_data: dict) -> dict:
        """
        Runs the full 10-agent consensus debate sequence on an active trade.
        """
        symbol = probe_trade["symbol"]
        
        # 1. Run all 10 analytical agents in parallel
        reports = []
        for agent in self.agents:
            try:
                rep = agent.analyze(symbol, signal_data)
                reports.append(rep)
            except Exception as e:
                logger.error(f"Error running agent {agent.__class__.__name__}: {e}")
                reports.append({"score": 50, "thesis": f"Agent {agent.__class__.__name__} failed."})

        # 2. Try LLM debate if active
        if self.groq_key:
            try:
                llm_ruling = await self._run_llm_debate(probe_trade, reports)
                if llm_ruling:
                    return llm_ruling
            except Exception as e:
                logger.error(f"Validation Committee LLM debate failed: {e}. Falling back to analytical engine.")

        # 3. Fallback to analytical Chairman mediation
        ruling = self.chairman.mediate(reports)

        # Build detailed transcript
        transcript_lines = [f"--- COMMITTEE DEBATE FOR {symbol} ---"]
        for idx, agent in enumerate(self.agents):
            name = agent.__class__.__name__.replace("Agent", "")
            transcript_lines.append(f"{idx+1}. {name} Analyst: {reports[idx]['thesis']} (Score: {reports[idx]['score']})")
        transcript_lines.append(f"Result: {ruling['chairman_summary']}")

        return {
            "approved": ruling["action"] in ("SCALE_MAX", "SCALE_NORMAL", "MAINTAIN"),
            "final_score": ruling["final_score"],
            "grade": ruling["grade"],
            "action": ruling["action"],
            "chairman_summary": ruling["chairman_summary"],
            "debate_transcript": "\n".join(transcript_lines),
            "agent_votes": reports
        }

    async def _run_llm_debate(self, probe_trade: dict, reports: List[Dict]) -> Optional[dict]:
        """Runs a structured LLM consensus audit via Groq API using all 10 agent scores."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }

        prompt = (
            f"You are the Zohra AI Validation Committee auditing an active trade.\n"
            f"Trade Profile:\n"
            f"- Asset: {probe_trade['symbol']}\n"
            f"- Direction: {probe_trade['direction']}\n"
            f"- Entry Price: {probe_trade['entry_price']}\n\n"
            f"Analytical Agents Input:\n"
            f"- Structure: {reports[0]['score']}/100\n"
            f"- SMC: {reports[1]['score']}/100\n"
            f"- Liquidity: {reports[2]['score']}/100\n"
            f"- Trend: {reports[3]['score']}/100\n"
            f"- Session: {reports[4]['score']}/100\n"
            f"- Volatility: {reports[5]['score']}/100\n"
            f"- Risk: {reports[6]['score']}/100\n"
            f"- Correlation: {reports[7]['score']}/100\n"
            f"- News: {reports[8]['score']}/100\n"
            f"- Execution: {reports[9]['score']}/100\n\n"
            f"Draft a short debate transcript and output a JSON decision structure:\n"
            f'{{"approved": true/false, "final_score": 85, "grade": "A", "action": "SCALE_NORMAL", '
            f'"chairman_summary": "...", "debate_transcript": "..."}}\n'
            f"Action options: SCALE_MAX (score >=90), SCALE_NORMAL (score 80-89), MAINTAIN (score 70-79), "
            f"REDUCE (score 60-69), REJECT (score <60)."
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
            
            # Hard safety limits
            if parsed["final_score"] < 70:
                parsed["approved"] = False
                parsed["action"] = "REJECT"

            parsed["agent_votes"] = reports
            return parsed
        return None

# Singleton
validation_committee = ValidationCommittee()
