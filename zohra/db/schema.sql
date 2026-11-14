-- Zohra Trading Engine — Production Schema
-- Compatible with PostgreSQL and SQLite (minor type differences handled in migrations)

-- ─── TRADES ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id                  SERIAL PRIMARY KEY,          -- INTEGER PRIMARY KEY AUTOINCREMENT in SQLite
    trade_id            TEXT NOT NULL UNIQUE,
    timestamp_open      TIMESTAMPTZ NOT NULL,
    timestamp_close     TIMESTAMPTZ,
    symbol              TEXT NOT NULL,
    direction           TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price         REAL NOT NULL,
    stop_loss           REAL NOT NULL,
    take_profit         REAL NOT NULL,
    exit_price          REAL,
    profit_loss         REAL,
    risk_reward_ratio   REAL,
    confidence_score    REAL NOT NULL,
    session             TEXT,
    market_regime       TEXT,
    strategy            TEXT NOT NULL,
    news_status         TEXT DEFAULT 'unknown',
    reason_for_entry    TEXT NOT NULL,
    reason_for_exit     TEXT,
    mt5_ticket          BIGINT,
    broker              TEXT NOT NULL DEFAULT 'mt5',
    asset_class         TEXT NOT NULL DEFAULT 'forex',
    position_size_lots  REAL NOT NULL DEFAULT 0.01,
    risk_usd            REAL DEFAULT 0,
    requested_price     REAL,
    slippage_points     REAL,
    entry_spread_points REAL,
    execution_latency_ms REAL,
    metadata            TEXT DEFAULT '{}',           -- JSON
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_open ON trades(timestamp_open);
CREATE INDEX IF NOT EXISTS idx_trades_close ON trades(timestamp_close);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy);
CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session);
CREATE INDEX IF NOT EXISTS idx_trades_regime ON trades(market_regime);

-- ─── REJECTED TRADES ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rejected_trades (
    id                    SERIAL PRIMARY KEY,
    timestamp             TIMESTAMPTZ NOT NULL,
    symbol                TEXT NOT NULL,
    confidence_score      REAL NOT NULL,
    failed_conditions     TEXT NOT NULL,             -- JSON array
    reason_for_rejection  TEXT NOT NULL,
    session               TEXT,
    market_regime         TEXT,
    strategy              TEXT,
    news_status           TEXT,
    score_breakdown       TEXT DEFAULT '{}',         -- JSON
    metadata              TEXT DEFAULT '{}',
    created_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rejected_symbol ON rejected_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_rejected_time ON rejected_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_rejected_strategy ON rejected_trades(strategy);

-- ─── EQUITY CURVE ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS equity_curve (
    id            SERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    equity        REAL NOT NULL,
    open_pnl      REAL DEFAULT 0,
    daily_pnl     REAL DEFAULT 0,
    monthly_pnl   REAL DEFAULT 0,
    drawdown_pct  REAL DEFAULT 0,
    broker        TEXT DEFAULT 'mt5'
);

CREATE INDEX IF NOT EXISTS idx_equity_time ON equity_curve(timestamp);

-- ─── SIGNALS (pre-execution intent) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    symbol          TEXT NOT NULL,
    direction       TEXT,
    signal_type     TEXT NOT NULL,
    price           REAL,
    confidence_score REAL,
    strategy        TEXT,
    executed        BOOLEAN DEFAULT FALSE,
    trade_id        TEXT,
    metadata        TEXT DEFAULT '{}'
);

-- ─── SYSTEM LOGS ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_logs (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    level       TEXT NOT NULL,
    source      TEXT DEFAULT 'zohra',
    message     TEXT NOT NULL,
    metadata    TEXT DEFAULT '{}'
);

-- ─── NEWS EVENTS (future integration) ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_events (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    currency    TEXT NOT NULL,
    impact      TEXT NOT NULL,
    title       TEXT NOT NULL,
    actual      TEXT,
    forecast    TEXT,
    previous    TEXT,
    blackout    BOOLEAN DEFAULT FALSE
);

-- ─── BROKER ACCOUNTS (multi-broker future) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS broker_accounts (
    id          SERIAL PRIMARY KEY,
    broker      TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    label       TEXT,
    is_active   BOOLEAN DEFAULT TRUE,
    metadata    TEXT DEFAULT '{}',
    UNIQUE(broker, account_id)
);

-- ─── AGENT ACTIONS (AI agent audit trail) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_actions (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    agent_id    TEXT NOT NULL,
    action_type TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    result      TEXT,
    trade_id    TEXT
);
