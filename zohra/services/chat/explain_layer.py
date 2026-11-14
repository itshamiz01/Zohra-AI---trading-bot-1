import logging
import json
import requests
from typing import Dict, Any, Optional
import zohra.config.settings as settings

logger = logging.getLogger("zohra.services.chat.explain")

# OpenRouter & Groq AI Providers


# ──────────────────────────────────────────────────────────────
#  ZOHRA AI SYSTEM PROMPT — This is the personality & knowledge
# ──────────────────────────────────────────────────────────────
ZOHRA_SYSTEM_PROMPT = """You are **Zohra AI**, the intelligence layer of the Zohra Autonomous Trading Command Center.

## WHO YOU ARE
- You are a personal AI trading assistant built into an autonomous MT5 trading bot.
- You trade Forex pairs (EURUSD, GBPUSD, USDJPY, etc.) and Metals (XAUUSD Gold, XAGUSD Silver).
- You use Smart Money Concepts (SMC), market structure breaks, liquidity sweeps, and multi-timeframe confluence scoring.
- You have FULL access to the user's live trading data, account info, open positions, trade history, and risk parameters.

## YOUR PERSONALITY
- You are professional but friendly — like a seasoned hedge fund analyst talking to their boss.
- You explain things clearly using numbers and data. Never vague.
- Use emojis sparingly but effectively (📈 📉 💰 🛡️ ⚠️ ✅ ❌).
- When discussing P&L, always show dollar amounts.
- When discussing trades, always reference the symbol, direction, and score.
- Keep responses concise but thorough (2-5 short paragraphs max).
- Use **bold** for key numbers and *italics* for emphasis.

## YOUR CAPABILITIES
You can answer questions about:
- Account balance, equity, margin, and overall health
- Today's P&L, win rate, number of trades
- Open positions and their current status
- Recent trade history and why trades were taken
- Why trades were rejected/skipped
- Strategy performance breakdowns
- Risk parameters and exposure limits
- Market analysis and regime detection
- Trading theory (SMC, supply/demand, ICT concepts)

## RULES
1. ALWAYS reference real data when available. Never make up numbers.
2. If data shows $0 trades today, say so honestly.
3. If a question is outside trading scope, politely redirect.
4. Never give financial advice — you explain what the BOT did and why.
5. Format responses in markdown for readability.
"""


class ExplainLayer:
    """
    Explainable AI (XAI) layer converting quantitative trading parameters,
    databases, and indicators into human-readable transparent reasoning chains.
    Uses Groq (free) or Gemini for AI synthesis, with robust local fallbacks.
    """

    def synthesize(self, intent: str, data: Dict[str, Any], raw_query: str = "") -> str:
        """
        Synthesize response. Priority order:
        1. Groq API (free, fast)
        2. Gemini API (free tier)
        3. Local smart templates
        """
        # Build the contextual prompt
        prompt = self._build_prompt(intent, data, raw_query)

        provider = getattr(settings, "CHAT_PROVIDER", "openrouter").lower()
        use_openrouter = (provider == "openrouter" and bool(settings.OPENROUTER_API_KEY)) or (bool(settings.OPENROUTER_API_KEY) and not (provider == "groq" and settings.GROQ_API_KEY))
        use_groq = (provider == "groq" and bool(settings.GROQ_API_KEY)) or (bool(settings.GROQ_API_KEY) and not use_openrouter)

        # Try OpenRouter first
        if use_openrouter:
            try:
                response = self._query_openrouter(prompt)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"OpenRouter synthesis failed: {e}")

        # Try Groq as fallback
        if use_groq:
            try:
                response = self._query_groq(prompt)
                if response:
                    return response
            except Exception as e:
                logger.warning(f"Groq synthesis failed: {e}")

        # Local fallback — always works
        return self._render_local_template(intent, data, raw_query)

    def _build_prompt(self, intent: str, data: Dict[str, Any], raw_query: str) -> str:
        """Build a rich contextual prompt for the AI."""

        if intent == "GENERAL_QNA":
            trading_ctx = data.get("trading_context", {})
            ctx_str = json.dumps(trading_ctx, indent=2, default=str) if trading_ctx else "No live data available"
            return (
                f"The user asks: \"{raw_query}\"\n\n"
                f"Here is the current live trading state of our system (for reference only):\n"
                f"```json\n{ctx_str}\n```\n\n"
                f"Answer the user's question. If the user's message is a greeting, friendly chat, general trading theory, "
                f"or questions about how the bot works, chat history, or security, address their query directly and naturally. "
                f"Do NOT reference or dump live account metrics (like balance, equity, win rate, or open positions) unless the user's "
                f"query is explicitly asking about them. Only use the live data block if relevant."
            )

        elif intent == "GET_POSITIONS":
            return (
                f"The user asked about open positions. Here is the data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Summarize the open positions clearly. Show symbol, direction, and current P&L for each."
            )

        elif intent == "GET_PERFORMANCE":
            return (
                f"The user asked about trading performance. Raw data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Provide a clear performance summary with win rate, net P&L, total trades, and any noteworthy patterns."
            )

        elif intent == "EXPLAIN_TRADE":
            return (
                f"The user asked about a specific trade. Trade details:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Explain why this trade was taken. Reference the confluence score, strategy, market regime, "
                f"entry/SL/TP levels, and the P&L outcome."
            )

        elif intent == "EXPLAIN_REJECTION":
            return (
                f"The user asked why a trade setup was rejected. Rejection data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Explain which conditions failed and which passed. Reference the score threshold."
            )

        elif intent == "ANALYZE_MARKET":
            return (
                f"The user asked for market analysis. Indicator data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Provide a professional market regime report. Interpret ADX, BB width, ATR, and trend direction."
            )

        elif intent == "QUERY_HIE_PATTERNS":
            return (
                f"The user requested HIE Pattern statistics. Data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Summarize the performance of these historical pattern setups. Show win rate, occurrences, and average R-multiple."
            )

        elif intent == "GET_HIE_PROFILE":
            return (
                f"The user requested HIE Symbol Profile for {data.get('symbol', 'the symbol')}. Data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Summarize the best/worst setups, sessions, and overall stats for the symbol."
            )

        elif intent == "QUERY_HIE_SIMILARITY":
            return (
                f"The user queried trade similarity context. Data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Explain what history says about this proposed trade based on the similarity matches, win rate, and past evidence."
            )

        elif intent == "GET_HIE_FAILURES":
            return (
                f"The user requested flagged failure patterns. Data:\n"
                f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Summarize these recurring losing setups and warn about trading these dangerous combinations."
            )

        else:
            return (
                f"User query: \"{raw_query}\"\n"
                f"Command executed: {intent}\n"
                f"Result data:\n```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
                f"Explain the result clearly."
            )

    def _query_openrouter(self, prompt: str) -> str:
        """Query OpenRouter API for intelligent responses."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/ZohraQuant/trading_bot",
            "X-Title": "Zohra AI Command Center"
        }
        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": ZOHRA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 600
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        choices = response.json().get("choices", [])
        if choices:
            return choices[0]["message"]["content"].strip()
        raise ValueError("Empty OpenRouter response")

    def _query_groq(self, prompt: str) -> str:
        """Query Groq API (free tier) for intelligent responses."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "system", "content": ZOHRA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 600
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()

        choices = response.json().get("choices", [])
        if choices:
            return choices[0]["message"]["content"].strip()
        raise ValueError("Empty Groq response")

    def _render_local_template(self, intent: str, data: Dict[str, Any], raw_query: str = "") -> str:
        """Smart local templates — always work offline."""

        if "error" in data:
            return f"⚠️ {data['error']}"

        if intent == "GET_POSITIONS":
            positions = data.get("positions", [])
            if not positions:
                return "📊 **No open positions** at the moment. The bot is scanning for setups."
            lines = ["### 📈 Open Positions\n"]
            total_pnl = 0
            for p in positions:
                pnl = p.get("pnl_usd", 0) or 0
                total_pnl += pnl
                emoji = "🟢" if pnl >= 0 else "🔴"
                lines.append(
                    f"{emoji} **{p.get('symbol', '?')}** {p.get('direction', '?')} | "
                    f"Entry: `{p.get('entry_price', '?')}` | P&L: **${pnl:.2f}**"
                )
            lines.append(f"\n💰 **Total Floating P&L:** ${total_pnl:.2f}")
            return "\n".join(lines)

        elif intent == "GET_PERFORMANCE":
            total = data.get("total_trades", 0)
            wins = data.get("wins", 0)
            wr = data.get("win_rate", data.get("win_rate_pct", 0))
            pnl = data.get("net_pnl", 0)
            days = data.get("period_days", 30)
            return (
                f"### 📊 Performance Summary (Last {days} days)\n\n"
                f"**Total Trades:** {total} | **Wins:** {wins} | **Losses:** {total - wins}\n"
                f"**Win Rate:** {wr}%\n"
                f"**Net P&L:** ${pnl:.2f}\n"
            )

        elif intent == "EXPLAIN_TRADE":
            symbol = data.get("symbol", "?")
            direction = data.get("direction", "?")
            pnl = data.get("pnl_usd")
            score = data.get("confidence_score", 0)
            strategy = data.get("strategy_used", "SMC")
            entry = data.get("entry_price", "?")
            sl = data.get("stop_loss", "?")
            tp = data.get("take_profit", "?")
            reason = data.get("reason_for_entry", "Confluence score above threshold")

            pnl_str = f"**P&L:** ${pnl:.2f}" if pnl is not None else "**Status:** Open"
            return (
                f"### 📈 Trade: {symbol} {direction}\n\n"
                f"**Strategy:** {strategy} | **Score:** {score}/100\n"
                f"**Entry:** {entry} | **SL:** {sl} | **TP:** {tp}\n"
                f"{pnl_str}\n\n"
                f"**Reason:** {reason}"
            )

        elif intent == "EXPLAIN_REJECTION":
            symbol = data.get("symbol", "?")
            reason = data.get("reason_for_rejection", "Score below threshold")
            score = data.get("confidence_score", 0)
            return (
                f"### 🛡️ Rejection: {symbol}\n\n"
                f"**Score:** {score}/100 (below minimum threshold)\n"
                f"**Reason:** {reason}"
            )

        elif intent == "ANALYZE_MARKET":
            symbol = data.get("symbol", "?")
            regime = data.get("regime", "UNKNOWN")
            direction = data.get("trend_direction", "NEUTRAL")
            adx = data.get("adx", 0)
            return (
                f"### 🔍 Market Analysis: {symbol}\n\n"
                f"**Regime:** {regime} | **Trend:** {direction}\n"
                f"**ADX:** {adx} | **ATR:** {data.get('atr', 'N/A')}\n"
            )

        elif intent == "GENERAL_QNA":
            # Smart offline fallback using available context
            ctx = data.get("trading_context", {})
            lines = ["### 🤖 Zohra AI\n"]

            account = ctx.get("account", {})
            if account:
                lines.append(f"**Account:** Balance ${account.get('balance', 0):.2f} | Equity ${account.get('equity', 0):.2f}")

            today = ctx.get("today", {})
            if today:
                lines.append(
                    f"**Today:** {today.get('trades', 0)} trades | "
                    f"Win Rate {today.get('win_rate', 0)}% | "
                    f"P&L ${today.get('net_pnl', 0):.2f}"
                )

            engine = ctx.get("engine_state", {})
            if engine:
                status = "🟢 Active" if not engine.get("halted") else "🔴 Halted"
                lines.append(f"**Engine:** {status}")

            open_pos = ctx.get("open_positions", 0)
            lines.append(f"**Open Positions:** {open_pos}")

            lines.append(
                "\n*Note: AI synthesis is currently offline. "
                "Showing live data snapshot. Try asking specific questions like "
                "'show open trades' or 'today's performance'.*"
            )
            return "\n".join(lines)

        elif intent in ("HALT_TRADING", "RESUME_TRADING"):
            success = data.get("success", False)
            action = "halted" if intent == "HALT_TRADING" else "resumed"
            emoji = "🛑" if intent == "HALT_TRADING" else "✅"
            if success:
                return f"{emoji} Trading engine **{action}** successfully."
            return f"⚠️ Could not {action.replace('ed', '')} the engine."

        elif intent in ("CLOSE_ALL", "CLOSE_PROFITABLE"):
            count = data.get("closed_count", 0)
            return f"✅ Closed **{count}** position(s) successfully."

        elif intent == "MODIFY_RISK":
            if data.get("success"):
                return f"✅ Risk per trade updated to **{data.get('new_risk_pct', 0)}%**."
            return f"⚠️ Could not update risk: {data.get('error', 'Unknown error')}"

        elif intent == "QUERY_HIE_PATTERNS":
            patterns = data.get("patterns", [])
            if not patterns:
                return "📊 **No historical patterns found** matching the criteria in HIE Database."
            lines = ["### 🏛️ HIE Pattern Statistics\n"]
            for idx, p in enumerate(patterns[:5]):
                lines.append(
                    f"{idx+1}. **{p.get('symbol')} {p.get('setup_type')}** | {p.get('direction')} | "
                    f"Win Rate: **{p.get('win_rate')}%** ({p.get('wins')}/{p.get('occurrences')} trades) | "
                    f"Avg RR: **{p.get('avg_rr')}R**"
                )
            return "\n".join(lines)

        elif intent == "GET_HIE_PROFILE":
            symbol = data.get("symbol", "?")
            profile = data.get("profile", {})
            memory = data.get("memory", {})
            if not profile:
                return f"📊 **No HIE profile found** for {symbol}."
            return (
                f"### 🏛️ HIE Symbol Profile: {symbol}\n\n"
                f"- **Best Session:** {profile.get('best_session', 'N/A')} | **Worst Session:** {profile.get('worst_session', 'N/A')}\n"
                f"- **Best Timeframe:** {profile.get('best_timeframe', 'N/A')} | **Worst Timeframe:** {profile.get('worst_timeframe', 'N/A')}\n"
                f"- **Best Setup:** {profile.get('best_setup', 'N/A')} | **Worst Setup:** {profile.get('worst_setup', 'N/A')}\n"
                f"- **Overall Win Rate:** **{profile.get('overall_win_rate', 0)}%**\n"
                f"- **Overall Avg RR:** **{profile.get('overall_avg_rr', 0)}R**\n\n"
                f"🧠 *Market Memory Summary:* {memory.get('total_memory_entries', 0)} strong/weak setups indexed."
            )

        elif intent == "QUERY_HIE_SIMILARITY":
            sim = data.get("similarity", {})
            if not sim or not sim.get("data_available"):
                return "📊 **No historical similarity matches found** for this setup."
            evidence_lines = []
            for ev in sim.get("historical_evidence", []):
                outcome_emoji = "🟢" if ev.get("outcome") == "WIN" else "🔴"
                evidence_lines.append(
                    f"  - {outcome_emoji} {ev.get('timestamp')} | Outcome: **{ev.get('outcome')}** ({ev.get('pnl_r'):+.1f}R)"
                )
            evidence_str = "\n".join(evidence_lines) if evidence_lines else "  - None"
            return (
                f"### 🏛️ Trade Similarity Match: {sim.get('symbol')} {sim.get('direction')}\n\n"
                f"- **Matches Found:** {sim.get('match_count')} past setups\n"
                f"- **Historical Win Rate:** **{sim.get('win_rate')}%** ({sim.get('wins')}/{sim.get('match_count')})\n"
                f"- **Average RR:** **{sim.get('avg_rr')}R**\n"
                f"- **Best Aligning Session:** {sim.get('best_session')}\n"
                f"- **HIE Confidence Level:** **{sim.get('confidence')}**\n\n"
                f"📋 *Recent Matches:*\n{evidence_str}"
            )

        elif intent == "GET_HIE_FAILURES":
            failures = data.get("failures", [])
            if not failures:
                return "🛡️ **No critical failure patterns flagged** in memory. Trading environment is clear."
            lines = ["### 🛡️ Flagged Failure Patterns (Repeated Losses)\n"]
            for idx, f in enumerate(failures[:5]):
                lines.append(
                    f"{idx+1}. ⚠️ **{f.get('failure_signature')}** | "
                    f"Occurrences: **{f.get('occurrences')}** | "
                    f"Fail Rate: **{f.get('fail_rate')}%** | "
                    f"Avg Loss: **{f.get('avg_loss'):.2f} USD**"
                )
            return "\n".join(lines)

        else:
            return f"✅ Command `{intent}` executed. Result: `{json.dumps(data, default=str)}`"
