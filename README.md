<<<<<<< HEAD
# Forex Trading Bot

## Zohra Assistant Upgrade

The existing dashboard and assistant now include a permission-controlled capability catalog, confirmed actions, real process/network reads, verified local PDF/Word/Excel creation, read-only Python source inspection and execution history. The universal Windows/Android roadmap is still in progress; unsupported features are labeled explicitly.

- [Architecture and integration plan](docs/zohra-universal-architecture.md)
- [Requested-feature status matrix](docs/zohra-integration-matrix.md)
- [Validation results and tab/backend map](docs/zohra-foundation-validation.md)
- [Document creation, download and regression validation](docs/zohra-documents-validation.md)
- [Verified local PDF reading and search](docs/zohra-pdf-inspection-validation.md)
- [Local project code inspection](docs/zohra-code-inspection-validation.md)

**Strategy:** EMA Crossover + ATR Filter  
**Timeframe:** 1 Hour  
**Mode:** Paper Trading (MetaTrader 5 Demo)  

---

## ⚠️ CRITICAL WARNINGS

1. **This is PAPER TRADING only.** No real money is at risk.
2. **Past performance ≠ future results.** The strategy may lose money.
3. **3-month minimum paper test required** before considering live capital.
4. **Never risk more than you can afford to lose completely.**

---

## Features

- ✅ Automated 1H forex trading on 5 major pairs
- ✅ Strict risk management (1% per trade, max 3 positions)
- ✅ ATR-based dynamic stops and targets
- ✅ Telegram command interface for monitoring
- ✅ SQLite logging and performance analytics
- ✅ Optional free LLM integration for Q&A

---

## Quick Start

### 1. Install Dependencies

```bash
cd trading_bot
pip install -r requirements.txt
```

### 2. Set Up MetaTrader 5 Account

1. Download and install MetaTrader 5 from the official site or your broker
2. Create a demo account (e.g., via File -> Open an Account)
3. Note your login number, password, and server name

### 3. Configure Environment

```bash
# Copy example and fill in your credentials
cp .env.example .env
# Edit .env with your actual values
```

Or set directly:
```bash
export MT5_LOGIN="12345678"
export MT5_PASSWORD="your_demo_password"
export MT5_SERVER="Broker-Demo"
```

### 4. (Optional) Set Up Telegram

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create new bot, copy token
3. Message your bot `/start`
4. Get your chat ID: visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Add to `.env`:
```bash
TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
TELEGRAM_CHAT_ID="123456789"
```

### 5. Run the Bot

```bash
python main.py
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Account balance, equity, open positions |
| `/history [n]` | Last n trades (default 10) |
| `/equity` | 30-day equity curve summary |
| `/stats` | Full performance statistics |
| `/why EURUSD` | Last signal reason for a pair |
| `/pause` | Stop opening new trades |
| `/resume` | Resume trading |
| `/help` | Show all commands |

---

## Strategy Details

### Entry Rules
- **LONG:** Fast EMA (20) crosses above Slow EMA (50) + price above both EMAs + ATR > minimum
- **SHORT:** Fast EMA crosses below Slow EMA + price below both EMAs + ATR > minimum

### Exit Rules
- **Stop Loss:** 1.5 × ATR from entry
- **Take Profit:** 3.0 × ATR from entry (2:1 minimum R/R)
- **Trailing Stop:** Move to breakeven at +1× ATR, trail at 1.5× ATR
- **Time Stop:** Close after 5 days (120 hours)
- **Reverse Signal:** Close on opposite crossover

### Risk Management
- 1% risk per trade
- Maximum 3 open positions
- Daily loss limit: 3% (pauses for 24h)
- Monthly loss limit: 10% (pauses for month)
- No weekend positions (close Friday 5pm EST)
- Correlated pair filter

---

## Project Structure

```
trading_bot/
├── main.py              # Entry point
├── config.py            # Settings and environment
├── database.py          # SQLite logging
├── data_feed.py         # MetaTrader 5 data feed
├── strategy.py          # EMA+ATR signal logic
├── risk_manager.py      # Position sizing, limits
├── executor.py          # Order execution
├── telegram_bot.py      # Command interface
├── scheduler.py         # Main trading loop
├── llm_interface.py     # Optional AI Q&A
├── requirements.txt     # Dependencies
├── .env.example         # Environment template
└── logs/
    └── trades.db        # SQLite database
```

---

## Expected Performance (Realistic)

| Metric | Target | Reality Check |
|--------|--------|---------------|
| Win Rate | 45-55% | Most trades will lose |
| Avg Winner | 2-3× avg loser | Winners must be bigger |
| Annual Return | 10-30% | With significant variance |
| Max Drawdown | 15-25% | Prepare mentally for this |

**If you cannot accept losing 25% of your account, do not trade.**

---

## Troubleshooting

### "Failed to fetch account summary"
- Check MT5 credentials in .env
- Ensure MetaTrader 5 desktop application is open and logged in
- Verify terminal connection status

### No trades opening
- Normal during low volatility
- Check `/status` for trading state
- Ensure not paused or at loss limits

### Telegram not working
- Bot token must be exact (copy from BotFather)
- Chat ID is numeric, not username
- Send `/start` to bot first

---

## License

MIT License — Use at your own risk. This software is for educational purposes only. The authors are not responsible for any financial losses.
=======
# Zohra-AI---trading-bot-1
>>>>>>> 999ffceaf09d9ba27253ae240bf99527c238b4ef
