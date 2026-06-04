"""
Free LLM Integration (Optional)
Uses Groq's free tier for general trading questions.
NOT for real-time trade reasoning — too slow and rate-limited.
"""

import requests
import os
from typing import Optional
from config import GROQ_API_KEY, GROQ_MODEL, GROQ_MAX_TOKENS
from database import db

class LLMInterface:
    """
    Lightweight LLM wrapper for educational Q&A.
    Falls back to static responses if API unavailable.
    """

    def __init__(self):
        self.available = bool(GROQ_API_KEY)
        self.base_url = "https://api.groq.com/openai/v1"
        self.static_knowledge = self._load_knowledge()

    def _load_knowledge(self) -> dict:
        """Static knowledge base for common questions"""
        return {
            "what is ema": 
                "EMA (Exponential Moving Average) gives more weight to recent prices. "
                "Our bot uses EMA 20 (fast) and EMA 50 (slow). When fast crosses above slow, "
                "it's a potential buy signal.",

            "what is atr": 
                "ATR (Average True Range) measures market volatility. "
                "We use it to set stop losses (1.5x ATR) and take profits (3x ATR). "
                "Higher ATR = wider stops = fewer but larger trades.",

            "what is risk per trade": 
                "We risk 1% of account equity per trade. If you have $10,000, "
                "each trade risks $100 maximum. This means you can lose 10 trades in a row "
                "and still have 90% of your capital.",

            "why 1 hour": 
                "1H timeframe balances noise reduction with enough trading opportunities. "
                "Shorter timeframes have more false signals. Longer timeframes have fewer trades. "
                "1H is where retail traders can still compete without HFT infrastructure.",

            "what is drawdown": 
                "Drawdown is the peak-to-trough decline in your account. "
                "A 20% drawdown means your account fell 20% from its highest point. "
                "Our bot stops trading at 10% monthly drawdown to prevent ruin.",

            "how does the bot work": 
                "The bot checks every hour for EMA crossovers on 5 major forex pairs. "
                "If fast EMA crosses slow EMA with trend confirmation and sufficient volatility, "
                "it enters with a stop loss and take profit. Risk is strictly limited to 1% per trade.",

            "why forex": 
                "Forex is the most liquid market ($7.5 trillion daily volume), "
                "open 24/5, and accessible with small capital via micro lots. "
                "However, leverage makes it dangerous without strict risk control.",

            "what is paper trading": 
                "Paper trading uses simulated money with real market prices. "
                "You see exactly how the strategy performs without risking capital. "
                "We require 3+ months of profitable paper trading before any live capital.",

            "martingale": 
                "Martingale means doubling bet size after each loss. "
                "It is mathematically guaranteed to blow up your account. "
                "The video you saw uses this — that's why it's fake. Our bot NEVER does this.",

            "win rate": 
                "Our target win rate is 45-55%. This sounds low, but with 2:1 reward/risk, "
                "you only need 34% win rate to break even. The edge comes from letting winners run "
                "and cutting losers quickly.",

            "leverage": 
                "Leverage amplifies both gains and losses. 30:1 leverage means a 3.3% move "
                "against you wipes the account. Our bot uses position sizing, not leverage, "
                "to control risk. Maximum effective leverage is well under 5:1.",

            "correlated pairs": 
                "EUR/USD and GBP/USD move similarly (~85% correlation). "
                "Trading both in the same direction doubles risk. Our bot limits exposure "
                "to prevent this cluster risk.",
        }

    def ask(self, question: str) -> str:
        """
        Answer a trading question.
        Tries static knowledge first, then LLM if available.
        """
        question_lower = question.lower().strip()

        # Check static knowledge first
        for key, answer in self.static_knowledge.items():
            if key in question_lower:
                return f"🧠 {answer}"

        # Try LLM if available
        if self.available:
            return self._llm_query(question)

        # Fallback
        return (
            "❓ I don't have a specific answer for that.\n"
            "Try asking about: EMA, ATR, risk per trade, drawdown, "
            "how the bot works, paper trading, or martingale.\n"
            "Or set a GROQ_API_KEY for expanded AI answers."
        )

    def _llm_query(self, question: str) -> str:
        """Query Groq LLM API"""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a helpful trading education assistant. "
                                "Answer questions about forex trading, technical analysis, "
                                "risk management, and the EMA+ATR strategy. "
                                "Be concise, accurate, and warn about risks. "
                                "Never promise profits or give specific trade recommendations."
                            )
                        },
                        {"role": "user", "content": question}
                    ],
                    "max_tokens": GROQ_MAX_TOKENS,
                    "temperature": 0.3
                },
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                answer = result["choices"][0]["message"]["content"]
                return f"🤖 {answer}"

            elif response.status_code == 429:
                return "⏳ LLM rate limit reached. Try again later or ask a simpler question."

            else:
                db.log_system("ERROR", f"LLM API error: {response.status_code}")
                return "⚠️ LLM service temporarily unavailable."

        except Exception as e:
            db.log_system("ERROR", f"LLM query failed: {e}")
            return "⚠️ Could not reach LLM service."

    def explain_last_trade(self, trade_id: str) -> str:
        """Explain why a specific trade was taken"""
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
        row = cursor.fetchone()

        if not row:
            return "Trade not found."

        columns = [desc[0] for desc in cursor.description]
        trade = dict(zip(columns, row))

        return (
            f"📋 <b>TRADE EXPLANATION: {trade['trade_id']}</b>\n\n"
            f"Symbol: {trade['symbol']}\n"
            f"Direction: {trade['direction']}\n"
            f"Entry: {trade['entry_price']:.5f}\n"
            f"Stop: {trade['stop_price']:.5f}\n"
            f"Target: {trade['target_price']:.5f}\n\n"
            f"<b>Why this trade?</b>\n"
            f"EMA Fast ({trade['ema_fast']:.5f}) crossed "
            f"{'above' if trade['direction'] == 'LONG' else 'below'} "
            f"EMA Slow ({trade['ema_slow']:.5f}).\n"
            f"ATR was {trade['atr']:.5f}, indicating sufficient volatility.\n"
            f"Risk was capped at ${trade['risk_usd']:.2f} ({trade['risk_usd']/10000*100:.1f}% of $10K).\n\n"
            f"Result: ${trade['pnl_usd']:.2f} ({trade['exit_reason']})"
        )

# Singleton instance
llm = LLMInterface()
