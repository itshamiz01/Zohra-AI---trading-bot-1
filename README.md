# Zohra AI — Autonomous Forex & Gold Trading Bot

> A multi-agent quantitative trading engine for Forex and XAU/USD (gold), with strict risk controls, a real-time FastAPI command-center dashboard, and a Telegram control interface. Built for **paper trading on MetaTrader 5 demo accounts** — no real money is traded by default.

**Author:** Hamid Ansari ([@itshamiz01](https://github.com/itshamiz01)) — software engineer building AI systems, trading automation and full-stack products.

---

## About this project

Zohra AI is an autonomous trading system that watches five major currency pairs plus gold on the 1-hour timeframe, scores trade setups with an EMA-crossover + ATR-volatility strategy, and only executes when its risk gates allow it. It was designed safety-first: position sizing is fixed-fractional, losses are capped daily and monthly, and a kill switch can halt all trading instantly from the dashboard or Telegram.

The system runs in two parts:

1. **Trading engine (Windows + MetaTrader 5)** — the full bot runs on a Windows machine connected to an MT5 terminal, where it analyses markets, manages open positions and logs every decision to SQLite.
2. **Command-center API & dashboard (FastAPI)** — a web dashboard ("ZOHRA AI OS // COMMAND CENTER") and 100+ REST/WebSocket endpoints for account status, trades, analytics, risk gates and controls. This part is deployed on Vercel in demo mode (no MT5 terminal attached, so it serves the dashboard and API without placing trades).

## What it does

- ✅ Automated 1H trading on 5 major Forex pairs + gold (XAU/USD)
- ✅ EMA (20/50) crossover entries filtered by ATR volatility
- ✅ Strict risk management — 1% risk per trade, max 3 open positions, 3% daily / 10% monthly loss limits that auto-pause trading
- ✅ ATR-based dynamic stop-loss (1.5× ATR) and take-profit (3.0× ATR), trailing stops and time stops
- ✅ Multi-agent design — separate agents for market analysis, risk, execution, news, performance and research
- ✅ Real-time dashboard with fleet/account views, equity curve, risk gates and a kill switch
- ✅ Telegram commands (`/status`, `/history`, `/equity`, `/stats`, `/pause`, `/resume`, `/why EURUSD`)
- ✅ SQLite trade journal and performance analytics; optional PostgreSQL and Groq LLM Q&A

## Tech stack

Python · FastAPI · pandas / NumPy · MetaTrader 5 API · SQLite (PostgreSQL optional) · Telegram Bot API · Vercel (dashboard/API hosting)

## ⚠️ Critical warnings

1. **Paper trading only.** This project is for education and research. No real money should be at risk.
2. **Past performance ≠ future results.** The strategy can and will have losing periods.
3. A **3-month minimum paper test** is recommended before even considering live capital.
4. **Never risk money you cannot afford to lose completely.**

## Quick start (full engine, Windows)

```bash
pip install -r requirements.txt   # full local stack incl. MetaTrader 5
cp .env.example .env              # fill in your MT5 DEMO login, password and server
python main.py                    # demo mode by default
```

You need MetaTrader 5 installed and running with a demo account. Optional: add a Telegram bot token and chat ID to `.env` for alerts and commands.

## Dashboard / API only

```bash
pip install fastapi "uvicorn[standard]" pydantic pandas numpy python-dotenv requests pytz matplotlib groq
uvicorn zohra.api.app:app --port 8000
# open http://localhost:8000  →  ZOHRA AI OS // COMMAND CENTER
# interactive API docs at http://localhost:8000/docs
```

On Vercel, `pyproject.toml` points the deployment at `zohra.api.app:app`; the Windows-only packages in `requirements.txt` (MetaTrader 5, pywin32, voice) are intentionally not part of the web deployment.

## Project structure

```
├── main.py               # Trading engine entry point (demo / live / simulated)
├── strategy.py           # EMA + ATR signal logic
├── data_feed.py          # MetaTrader 5 market data feed
├── scheduler.py          # Main trading loop
├── telegram_bot.py       # Telegram command interface
├── llm_interface.py      # Optional LLM Q&A
├── zohra/                # Production engine package
│   ├── agents/           # Analysis, risk, execution, news & research agents
│   ├── api/              # FastAPI app + command-center dashboard
│   ├── brokers/          # MT5 broker adapter + simulated broker
│   ├── config/           # Settings and strategy configuration
│   ├── db/               # SQLite/PostgreSQL schema and logging
│   └── validation/       # Backtester, replay and paper-trading engines
├── trading_bot2/         # Earlier standalone bot implementation
└── docs/                 # Architecture and validation notes
```

## Strategy in brief

- **Long:** EMA-20 crosses above EMA-50, price above both, ATR above minimum
- **Short:** EMA-20 crosses below EMA-50, price below both, ATR above minimum
- **Exits:** stop 1.5× ATR · target 3.0× ATR · trailing stop after +1× ATR · 5-day time stop · opposite-signal close · no weekend positions

## License

MIT — use at your own risk. Educational software; the author is not responsible for any financial losses.
