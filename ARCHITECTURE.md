# Zohra Trading Engine — Production Architecture

## Overview

Zohra is a production-grade autonomous Forex and XAUUSD trading engine built for MetaTrader 5. It unifies all existing project features (EMA+ATR swing bot, Zohra SMC scanners, gold scalpers) into a modular package with full trade logging, rejection analytics, performance metrics, and reporting.

**Broker:** MetaTrader 5 only. All legacy third-party broker references have been removed.

---

## Complete Folder Structure

```
trading_bot/
├── zohra/                          # Production package (NEW)
│   ├── __init__.py
│   ├── config/
│   │   ├── settings.py             # Central config, strategy profiles
│   │   └── __init__.py
│   ├── core/
│   │   ├── enums.py                # Direction, Regime, Session, Strategy
│   │   ├── models.py               # TradeRecord, RejectedTradeRecord
│   │   └── __init__.py
│   ├── db/
│   │   ├── schema.sql              # Full PostgreSQL/SQLite schema
│   │   ├── connection.py           # DB factory with fallback
│   │   └── repositories/
│   │       ├── trades.py
│   │       ├── rejections.py
│   │       └── equity.py
│   ├── logging/
│   │   ├── trade_logger.py         # Auto trade logging (17 fields)
│   │   └── rejection_logger.py     # Rejected opportunity logging
│   ├── analytics/
│   │   └── performance.py          # Win rate, PF, Sharpe, DD, etc.
│   ├── reporting/
│   │   ├── report_generator.py     # Daily/weekly/monthly HTML+JSON
│   │   └── charts.py               # Matplotlib charts
│   ├── api/
│   │   └── app.py                  # FastAPI REST endpoints
│   ├── brokers/
│   │   ├── base.py                 # Abstract BrokerAdapter
│   │   └── mt5/
│   │       └── adapter.py          # MT5 implementation
│   ├── strategies/
│   │   ├── zohra_scoring_v5.py     # SMC scorer (from trading_bot2)
│   │   └── scalp_m5.py             # M5 scalper (from trading_bot2)
│   ├── services/
│   │   └── engine.py               # ZohraEngine orchestrator
│   ├── integrations/
│   │   ├── ai_agent.py             # AI assistant bridge
│   │   ├── voice.py                # Voice command handler
│   │   └── news.py                 # News analysis hook
│   ├── utils/
│   │   ├── mt5_utils.py            # Shared MT5 helpers
│   │   └── session.py              # Session detection
│   └── tools/
│       └── analyze_rejections.py     # Rejection CLI
│
├── zohra_main.py                   # Production CLI entry point
├── ARCHITECTURE.md                 # This document
│
├── # Legacy scripts (preserved, migrate incrementally)
├── main.py                         # H1 EMA+ATR bot launcher
├── zohra_engine.py                 # 24/7 SMC agent (flagship)
├── gold_scalper_pro.py             # XAUUSD scalp engine
├── zohra_v4.py, zohra_precision_v3.py, zohra_manager.py
├── config.py, database.py, data_feed.py, executor.py
├── scheduler.py, strategy.py, risk_manager.py
├── telegram_bot.py, llm_interface.py
│
├── trading_bot2/                   # ARCHIVE — features extracted to zohra/
└── logs/
    ├── zohra.db                    # SQLite (default)
    └── reports/                    # Generated reports + charts
```

---

## Database Schema

### `trades` — Full Trade Logging (Requirement #1)

| Column | Type | Description |
|--------|------|-------------|
| trade_id | TEXT UNIQUE | ZHR-XXXXXXXXXXXX |
| timestamp_open | TIMESTAMPTZ | Entry time |
| timestamp_close | TIMESTAMPTZ | Exit time |
| symbol | TEXT | EURUSD, XAUUSD |
| direction | TEXT | LONG / SHORT |
| entry_price | REAL | Fill price |
| stop_loss | REAL | SL level |
| take_profit | REAL | TP level |
| exit_price | REAL | Close price |
| profit_loss | REAL | Realized P&L |
| risk_reward_ratio | REAL | Planned R:R |
| confidence_score | REAL | 0–100 score |
| session | TEXT | asia/london/ny/overlap |
| market_regime | TEXT | trending/ranging/etc. |
| strategy | TEXT | zohra_v5, scalp_m5, etc. |
| news_status | TEXT | clear/blackout/etc. |
| reason_for_entry | TEXT | Human-readable |
| reason_for_exit | TEXT | SL/TP/trail/manual |
| mt5_ticket | BIGINT | MT5 position ticket |
| broker | TEXT | mt5 |
| asset_class | TEXT | forex/metals |
| position_size_lots | REAL | Volume |
| metadata | JSON | Extensible |

### `rejected_trades` — Rejected Opportunity Logging (Requirement #2)

| Column | Type |
|--------|------|
| timestamp | TIMESTAMPTZ |
| symbol | TEXT |
| confidence_score | REAL |
| failed_conditions | JSON array |
| reason_for_rejection | TEXT |
| session, market_regime, strategy, news_status | TEXT |
| score_breakdown | JSON |

### Supporting Tables

- `equity_curve` — Drawdown / Sharpe inputs
- `signals` — Pre-execution intent
- `system_logs` — Operational events
- `news_events` — Future calendar integration
- `broker_accounts` — Multi-broker future
- `agent_actions` — AI agent audit trail

### Database Backend

```
PostgreSQL (preferred)  →  set DATABASE_URL=postgresql://user:pass@host:5432/zohra
SQLite (fallback)       →  default logs/zohra.db when DATABASE_URL unset
```

---

## API Architecture

**Framework:** FastAPI  
**Base URL:** `http://127.0.0.1:8000`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | System health + DB backend |
| GET | `/trades` | Closed trade history |
| GET | `/trades/open` | Open positions (DB) |
| GET | `/trades/{trade_id}` | Single trade detail |
| GET | `/rejections` | Rejected setups |
| GET | `/analytics` | Full performance report |
| GET | `/analytics/daily` | Daily metrics |
| GET | `/analytics/weekly` | Weekly metrics |
| GET | `/analytics/monthly` | Monthly metrics |
| POST | `/reports/{period}` | Generate report + charts |
| GET | `/reports/{period}/latest` | Latest HTML report |
| POST | `/agents/action` | AI agent audit log |
| GET | `/news/status` | News integration hook |
| GET | `/brokers` | Broker registry |

**Start API:**
```bash
python zohra_main.py api
```

---

## Class Structure

```
BrokerAdapter (ABC)
└── MT5BrokerAdapter
    ├── connect / disconnect
    ├── get_candles / get_current_price
    ├── open_position / close_position / close_partial
    └── modify_stop

TradeRecord / RejectedTradeRecord (dataclasses)
├── to_db_dict()
└── compute_risk_reward()

TradeLogger ──► TradeRepository
RejectionLogger ──► RejectionRepository

PerformanceAnalytics
├── full_report()
├── daily() / weekly() / monthly()
├── _core_metrics() → win rate, PF, expectancy, Sharpe, DD
└── _group_performance() → session/pair/strategy

ReportGenerator ──► PerformanceAnalytics + charts

ZohraScoringEngine (SMC v5)
├── detect_regime()
├── score_setup() → TradeScore
└── evaluate() → approved/rejected

ScalpM5Engine (M5 scalper)
├── can_trade() → session/spread limits
└── generate_signal()

ZohraEngine (orchestrator)
├── evaluate_and_log()
├── execute_trade()
├── close_trade()
└── generate_report()

ZohraAgentBridge / VoiceCommandHandler / NewsAnalyzer
```

---

## Performance Analytics (Requirement #3)

| Metric | Implementation |
|--------|----------------|
| Win Rate | wins / total closed trades |
| Profit Factor | gross profit / gross loss |
| Expectancy | (win% × avg win) + (loss% × avg loss) |
| Drawdown | Peak-to-trough on equity curve |
| Sharpe Ratio | mean(PnL) / std(PnL) per trade |
| Avg Trade Duration | mean(close - open) in minutes |
| Session Performance | Group by `session` column |
| Pair Performance | Group by `symbol` |
| Strategy Performance | Group by `strategy` |

---

## Reporting Dashboard (Requirement #5)

| Report | Command | Output |
|--------|---------|--------|
| Daily | `python zohra_main.py report daily` | HTML + JSON + PNG charts |
| Weekly | `python zohra_main.py report weekly` | Same |
| Monthly | `python zohra_main.py report monthly` | Same |

Charts generated:
- Equity curve
- P&L by pair
- P&L by session
- P&L by strategy
- Win rate pie chart

Output: `logs/reports/{period}/{timestamp}/`

---

## Future Integration (Requirement #6)

| Integration | Status | Location |
|-------------|--------|----------|
| AI Agents | Hook ready | `zohra/integrations/ai_agent.py`, `/agents/action` API |
| Voice Commands | Hook ready | `zohra/integrations/voice.py` |
| News Analysis | Hook ready | `zohra/integrations/news.py`, `news_events` table |
| Multi-Broker | Interface ready | `BrokerAdapter` ABC, `broker_accounts` table |
| Multi-Asset | Schema ready | `asset_class` column, metals in config |

---

## Feature Extraction from trading_bot2

| Source (trading_bot2) | Extracted To | OANDA Removed |
|----------------------|--------------|---------------|
| zohra_enhanced_core.py | zohra/strategies/zohra_scoring_v5.py | ✅ |
| scalping_module.py | zohra/strategies/scalp_m5.py | ✅ MT5 symbols |
| analyze_rejections.py | zohra/tools/analyze_rejections.py | ✅ DB-backed |
| database.py | zohra/db/ (extended schema) | ✅ mt5_ticket |
| telegram_bot.py | Legacy + future wire to ZohraEngine | ✅ |
| llm_interface.py | Legacy + /ask future | ✅ |
| risk_manager.py | Preserved in root, profiles in settings | ✅ |
| scheduler.py | Pattern in ZohraEngine | ✅ |

**Not migrated (duplicates):** OANDA data_feed, executor, main.py — root already has MT5 versions.

---

## Production Implementation Plan

### Phase 1 — Foundation ✅ (This release)
- [x] `zohra/` package structure
- [x] PostgreSQL + SQLite schema
- [x] Trade + rejection logging
- [x] Performance analytics engine
- [x] Daily/weekly/monthly reports with charts
- [x] FastAPI skeleton
- [x] MT5 broker adapter
- [x] SMC v5 + M5 scalp strategies extracted
- [x] AI/voice/news integration hooks

### Phase 2 — Engine Integration (Next)
- [ ] Wire `zohra_engine.py` to `TradeLogger` + `RejectionLogger`
- [ ] Replace CSV journal with SQLite
- [ ] Rename `oanda_trade_id` → `mt5_ticket` in legacy `database.py`
- [ ] Connect `telegram_bot.py` to `ZohraEngine.get_status()`
- [ ] Add `/ask` command via `llm_interface.py`

### Phase 3 — Strategy Unification
- [ ] Extract `gold_scalper_pro.py` scoring into `zohra/strategies/gold_scalp.py`
- [ ] Extract `zohra_engine.py` SMC modules into `zohra/strategies/zohra_smc.py`
- [ ] Unified `PositionManager` from `zohra_manager.py`
- [ ] Multi-strategy scheduler with profile selector

### Phase 4 — Production Hardening
- [ ] PostgreSQL deployment + connection pooling
- [ ] Alembic migrations
- [ ] Structured logging (JSON)
- [ ] Health checks + Prometheus metrics
- [ ] Docker compose (MT5 bridge + API + DB)
- [ ] Backtest mode with same schema

### Phase 5 — Zohra AI Assistant
- [ ] Wire `ZohraAgentBridge` to assistant runtime
- [ ] Voice → `VoiceCommandHandler`
- [ ] Economic calendar API → `NewsAnalyzer`
- [ ] Real-time WebSocket feed for dashboard

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure (MT5 required)
cp .env.example .env
# Edit MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# Optional: PostgreSQL
# DATABASE_URL=postgresql://user:pass@localhost:5432/zohra

# Check status
python zohra_main.py status

# Generate daily report
python zohra_main.py report daily

# Analyze rejections
python zohra_main.py rejections

# Start API
python zohra_main.py api
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| MT5_LOGIN | Yes | MT5 account number |
| MT5_PASSWORD | Yes | MT5 password |
| MT5_SERVER | Yes | Broker server name |
| DATABASE_URL | No | PostgreSQL connection string |
| DB_PATH | No | SQLite path (default: logs/zohra.db) |
| TELEGRAM_BOT_TOKEN | No | Alerts |
| TELEGRAM_CHAT_ID | No | Alerts |
| GROQ_API_KEY | No | LLM Q&A |
| ZOHR_API_HOST | No | API bind host |
| ZOHR_API_PORT | No | API port (default 8000) |
