"""
╔══════════════════════════════════════════════════════╗
║           ZOHRA — DATABASE SCHEMA                    ║
║  Production-grade: SQLite (default) / PostgreSQL     ║
╚══════════════════════════════════════════════════════╝

Schema includes:
  - trades             → full trade lifecycle
  - rejected_trades    → every rejected opportunity
  - equity_curve       → account snapshots
  - performance_snapshots → daily/weekly/monthly summaries
  - system_logs        → structured logging
"""

import os
import sqlite3
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from contextlib import contextmanager

# Try PostgreSQL first, fall back to SQLite
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Import settings
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import (
    DB_PATH, USE_POSTGRES,
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB,
    POSTGRES_USER, POSTGRES_PASSWORD, LOG_DIR
)

logger = logging.getLogger("zohra.db")

# ════════════════════════════════════════════════
#  SQL SCHEMAS (compatible with both dialects)
# ════════════════════════════════════════════════

SQLITE_SCHEMA = """
-- ─── TRADES TABLE ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id             TEXT    UNIQUE NOT NULL,
    mt5_ticket           INTEGER,
    timestamp_open       TEXT    NOT NULL,
    timestamp_close      TEXT,
    symbol               TEXT    NOT NULL,
    direction            TEXT    NOT NULL,          -- LONG / SHORT
    entry_price          REAL    NOT NULL,
    exit_price           REAL,
    stop_loss            REAL    NOT NULL,
    take_profit          REAL    NOT NULL,
    position_size_lots   REAL    NOT NULL,
    risk_usd             REAL,
    pnl_usd              REAL,
    pnl_pct              REAL,
    risk_reward_ratio    REAL,
    confidence_score     INTEGER,                   -- 0-100
    quality_grade        TEXT,                      -- A+ / A / B
    session              TEXT,                      -- London/NewYork/Overlap/Asian
    market_regime        TEXT,                      -- Trending/Ranging/Breakout/etc.
    strategy_used        TEXT,                      -- SMC / Scalping / Gold
    news_status          INTEGER DEFAULT 0,         -- 0=clear, 1=high-impact nearby
    reason_for_entry     TEXT,
    reason_for_exit      TEXT,
    exit_reason_code     TEXT,                      -- SL_HIT/TP1_HIT/TP2_HIT/BE_HIT/MANUAL/TRAIL
    be_moved             INTEGER DEFAULT 0,
    half_closed          INTEGER DEFAULT 0,
    duration_minutes     INTEGER,
    requested_price      REAL,
    slippage_points      REAL,
    entry_spread_points  REAL,
    execution_latency_ms REAL,
    -- Score breakdown columns
    score_structure      INTEGER DEFAULT 0,
    score_liquidity      INTEGER DEFAULT 0,
    score_smc            INTEGER DEFAULT 0,
    score_trend          INTEGER DEFAULT 0,
    score_momentum       INTEGER DEFAULT 0,
    score_volatility     INTEGER DEFAULT 0,
    score_pullback       INTEGER DEFAULT 0,
    metadata             TEXT DEFAULT '{}'
);

-- ─── REJECTED TRADES TABLE ──────────────────────────────
CREATE TABLE IF NOT EXISTS rejected_trades (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT    NOT NULL,
    symbol               TEXT    NOT NULL,
    direction            TEXT,
    confidence_score     INTEGER,
    failed_conditions    TEXT,                      -- JSON array of failed filters
    reason_for_rejection TEXT    NOT NULL,
    regime               TEXT,
    structure_pass       INTEGER DEFAULT 0,
    liquidity_pass       INTEGER DEFAULT 0,
    momentum_pass        INTEGER DEFAULT 0,
    volume_pass          INTEGER DEFAULT 0,
    metadata             TEXT DEFAULT '{}'
);

-- ─── EQUITY CURVE TABLE ─────────────────────────────────
CREATE TABLE IF NOT EXISTS equity_curve (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    equity       REAL    NOT NULL,
    balance      REAL,
    open_pnl     REAL,
    daily_pnl    REAL,
    weekly_pnl   REAL,
    monthly_pnl  REAL
);

-- ─── PERFORMANCE SNAPSHOTS TABLE ────────────────────────
CREATE TABLE IF NOT EXISTS performance_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    period_type       TEXT NOT NULL,                -- daily / weekly / monthly
    period_start      TEXT NOT NULL,
    period_end        TEXT NOT NULL,
    total_trades      INTEGER DEFAULT 0,
    winning_trades    INTEGER DEFAULT 0,
    losing_trades     INTEGER DEFAULT 0,
    win_rate          REAL,
    profit_factor     REAL,
    expectancy        REAL,
    total_pnl         REAL,
    max_drawdown      REAL,
    sharpe_ratio      REAL,
    avg_duration_min  INTEGER,
    best_pair         TEXT,
    worst_pair        TEXT,
    best_session      TEXT,
    strategy_data     TEXT                          -- JSON: per-strategy breakdown
);

-- ─── SYSTEM LOGS TABLE ──────────────────────────────────
CREATE TABLE IF NOT EXISTS system_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL,
    level     TEXT    NOT NULL,
    module    TEXT,
    message   TEXT    NOT NULL
);

-- ─── AGENT DECISIONS TABLE ──────────────────────────────
CREATE TABLE IF NOT EXISTS agent_decisions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT    NOT NULL,
    proposal_id          TEXT    NOT NULL,
    symbol               TEXT    NOT NULL,
    direction            TEXT    NOT NULL,
    market_analysis_score INTEGER,
    news_agent_vote      TEXT    NOT NULL,
    news_agent_reason    TEXT,
    risk_agent_vote      TEXT    NOT NULL,
    risk_agent_lots      REAL,
    risk_agent_reason    TEXT,
    consensus_status     TEXT    NOT NULL,
    execution_ticket     INTEGER
);

-- ─── CHAT SESSIONS TABLE ────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    role         TEXT NOT NULL,              -- user / assistant
    message      TEXT NOT NULL,
    intent       TEXT,                       -- recognized intent if assistant
    parameters   TEXT                        -- JSON string of parsed variables
);

-- ─── LIVE OPPORTUNITIES TABLE ────────────────────────────
CREATE TABLE IF NOT EXISTS live_opportunities (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol               TEXT    NOT NULL,
    strategy             TEXT    NOT NULL,
    confidence_score     INTEGER NOT NULL,
    direction            TEXT    NOT NULL,
    entry_price          REAL    NOT NULL,
    stop_loss            REAL    NOT NULL,
    take_profit          REAL    NOT NULL,
    reasons              TEXT,
    registered_at        TEXT    NOT NULL
);

-- ─── CORRELATION MATRIX CACHE TABLE ──────────────────────
CREATE TABLE IF NOT EXISTS correlation_matrix_cache (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    matrix_json          TEXT    NOT NULL,
    updated_at           TEXT    NOT NULL
);

-- ─── INDEXES ────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_open      ON trades(timestamp_open);
CREATE INDEX IF NOT EXISTS idx_trades_strategy  ON trades(strategy_used);
CREATE INDEX IF NOT EXISTS idx_trades_session   ON trades(session);
CREATE INDEX IF NOT EXISTS idx_rejected_symbol  ON rejected_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_rejected_ts      ON rejected_trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_equity_time      ON equity_curve(timestamp);
CREATE INDEX IF NOT EXISTS idx_perf_type        ON performance_snapshots(period_type);
CREATE INDEX IF NOT EXISTS idx_logs_level       ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_agent_prop       ON agent_decisions(proposal_id);
CREATE INDEX IF NOT EXISTS idx_chat_session     ON chat_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_live_opp_score   ON live_opportunities(confidence_score);

-- ─── EXTENDED TABLES FOR INSTITUTIONAL COMMAND CENTER ───
CREATE TABLE IF NOT EXISTS trade_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    confluence_matrix TEXT,
    post_mortem_notes TEXT,
    ai_coach_verdict TEXT,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
);
CREATE TABLE IF NOT EXISTS trade_rejections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT,
    confidence_score INTEGER,
    reason_for_rejection TEXT NOT NULL,
    failed_conditions TEXT,
    market_regime TEXT,
    indicator_states TEXT
);
CREATE TABLE IF NOT EXISTS symbol_statistics (
    symbol TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    avg_win REAL DEFAULT 0.0,
    avg_loss REAL DEFAULT 0.0,
    avg_quality_score REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_statistics (
    strategy TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    avg_hold_time REAL DEFAULT 0.0,
    avg_rr REAL DEFAULT 0.0,
    expected_value REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_conditions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime TEXT UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    best_strategy TEXT,
    worst_strategy TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    strategy TEXT NOT NULL,
    direction TEXT NOT NULL,
    confidence_score INTEGER NOT NULL,
    status TEXT NOT NULL,
    decision_reason TEXT
);
CREATE TABLE IF NOT EXISTS signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    indicator_name TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    price REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT UNIQUE NOT NULL,
    execution_delay_ms INTEGER,
    latency_ms INTEGER,
    spread_at_entry REAL,
    spread_at_exit REAL,
    slippage_points REAL,
    partial_fills INTEGER DEFAULT 0,
    order_rejections INTEGER DEFAULT 0,
    broker_response_time_ms INTEGER
);
CREATE TABLE IF NOT EXISTS broker_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    broker_name TEXT NOT NULL,
    execution_speed_ms INTEGER,
    spread_history TEXT,
    spread_spikes INTEGER DEFAULT 0,
    connection_stability REAL DEFAULT 100.0,
    order_fill_quality REAL DEFAULT 100.0
);
CREATE TABLE IF NOT EXISTS decision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    trade_id TEXT,
    action TEXT NOT NULL,
    decision_matrix TEXT NOT NULL,
    memory_context_ids TEXT
);
CREATE TABLE IF NOT EXISTS decision_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    confidence_delta REAL DEFAULT 0.0,
    associated_trades TEXT
);
CREATE TABLE IF NOT EXISTS market_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    market_regime TEXT NOT NULL,
    volatility_atr REAL,
    bid_ask_spread REAL
);
CREATE TABLE IF NOT EXISTS learning_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    recommendation_text TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    applied INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pattern_discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_signature TEXT UNIQUE NOT NULL,
    confluences TEXT NOT NULL,
    occurrences INTEGER DEFAULT 0,
    success_rate REAL DEFAULT 0.0,
    avg_pnl REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS failure_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    failure_signature TEXT UNIQUE NOT NULL,
    confluences TEXT NOT NULL,
    occurrences INTEGER DEFAULT 0,
    fail_rate REAL DEFAULT 0.0,
    avg_loss REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS system_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cpu_usage REAL,
    ram_usage REAL,
    disk_usage REAL,
    db_health_status TEXT,
    mt5_connection_status TEXT,
    api_health_status TEXT
);
CREATE TABLE IF NOT EXISTS module_health (
    module_name TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    latency_ms REAL,
    last_activity TEXT NOT NULL,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_exposure (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    sector_exposures TEXT NOT NULL,
    currency_stack TEXT NOT NULL,
    margin_used REAL,
    free_margin REAL,
    margin_level REAL,
    leverage_utilization REAL
);
CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    action_taken TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_playbacks (
    trade_id TEXT PRIMARY KEY,
    candles_history TEXT NOT NULL,
    indicator_history TEXT NOT NULL,
    decision_timeline TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
);
CREATE TABLE IF NOT EXISTS session_analytics (
    session_name TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    net_pnl REAL DEFAULT 0.0,
    avg_score REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS timeframe_analytics (
    timeframe TEXT PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate REAL DEFAULT 0.0,
    net_pnl REAL DEFAULT 0.0,
    signal_quality REAL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS strategy_evolution_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    parameter_updates TEXT NOT NULL,
    optimizer_run_id TEXT
);
CREATE TABLE IF NOT EXISTS daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start TEXT UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS monthly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month_start TEXT UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl REAL DEFAULT 0.0,
    win_rate REAL DEFAULT 0.0,
    profit_factor REAL DEFAULT 0.0,
    summary TEXT
);

-- ─── HIE TABLES ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hie_candles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    open        REAL    NOT NULL,
    high        REAL    NOT NULL,
    low         REAL    NOT NULL,
    close       REAL    NOT NULL,
    volume      REAL    DEFAULT 0,
    spread      REAL    DEFAULT 0,
    UNIQUE(symbol, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS hie_setups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    setup_type  TEXT NOT NULL,
    direction   TEXT NOT NULL,
    session     TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss   REAL NOT NULL,
    take_profit REAL NOT NULL,
    atr         REAL DEFAULT 0,
    outcome_analyzed INTEGER DEFAULT 0,
    UNIQUE(symbol, timeframe, setup_type, direction, timestamp)
);

CREATE TABLE IF NOT EXISTS hie_setup_outcomes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    setup_id     INTEGER NOT NULL UNIQUE,
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    setup_type   TEXT NOT NULL,
    direction    TEXT NOT NULL,
    session      TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    entry_price  REAL NOT NULL,
    stop_loss    REAL NOT NULL,
    take_profit  REAL NOT NULL,
    risk_r       REAL NOT NULL,
    reached_0_5r INTEGER DEFAULT 0,
    reached_1r   INTEGER DEFAULT 0,
    reached_2r   INTEGER DEFAULT 0,
    reached_3r   INTEGER DEFAULT 0,
    reached_5r   INTEGER DEFAULT 0,
    is_win       INTEGER DEFAULT 0,
    pnl_r        REAL DEFAULT 0,
    mfe_r        REAL DEFAULT 0,
    mae_r        REAL DEFAULT 0,
    bars_held    INTEGER DEFAULT 0,
    FOREIGN KEY(setup_id) REFERENCES hie_setups(id)
);

CREATE TABLE IF NOT EXISTS hie_pattern_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    setup_type   TEXT NOT NULL,
    direction    TEXT NOT NULL,
    session      TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    occurrences  INTEGER DEFAULT 0,
    wins         INTEGER DEFAULT 0,
    losses       INTEGER DEFAULT 0,
    win_rate     REAL DEFAULT 0,
    avg_rr       REAL DEFAULT 0,
    avg_mfe_r    REAL DEFAULT 0,
    avg_mae_r    REAL DEFAULT 0,
    reach_1r_pct REAL DEFAULT 0,
    reach_2r_pct REAL DEFAULT 0,
    reach_3r_pct REAL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    UNIQUE(symbol, setup_type, direction, session, timeframe)
);

CREATE TABLE IF NOT EXISTS hie_market_memory (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    setup_type   TEXT NOT NULL,
    session      TEXT NOT NULL,
    direction    TEXT NOT NULL,
    occurrences  INTEGER DEFAULT 0,
    win_rate     REAL DEFAULT 0,
    avg_rr       REAL DEFAULT 0,
    memory_label TEXT,
    is_strong    INTEGER DEFAULT 0,
    is_weak      INTEGER DEFAULT 0,
    updated_at   TEXT NOT NULL,
    UNIQUE(symbol, setup_type, session, direction)
);

CREATE TABLE IF NOT EXISTS hie_symbol_profiles (
    symbol           TEXT PRIMARY KEY,
    best_session     TEXT,
    worst_session    TEXT,
    best_timeframe   TEXT,
    worst_timeframe  TEXT,
    best_setup       TEXT,
    worst_setup      TEXT,
    overall_win_rate REAL DEFAULT 0,
    overall_avg_rr   REAL DEFAULT 0,
    profile_json     TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hie_confidence_calibration (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    score_bucket TEXT NOT NULL UNIQUE,
    sample_size  INTEGER DEFAULT 0,
    actual_wins  INTEGER DEFAULT 0,
    actual_wr    REAL DEFAULT 0,
    expected_wr  REAL DEFAULT 0,
    calibrated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hie_similarity_cache (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash   TEXT UNIQUE NOT NULL,
    result_json  TEXT NOT NULL,
    cached_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hie_candles_sym_tf_ts ON hie_candles(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_hie_setups_sym ON hie_setups(symbol, timeframe, setup_type);
CREATE INDEX IF NOT EXISTS idx_hie_setups_session ON hie_setups(session);
CREATE INDEX IF NOT EXISTS idx_outcome_sym ON hie_setup_outcomes(symbol, setup_type, session);
CREATE INDEX IF NOT EXISTS idx_hie_pstats_sym ON hie_pattern_stats(symbol, setup_type);
CREATE INDEX IF NOT EXISTS idx_hie_pstats_sess ON hie_pattern_stats(session);
CREATE INDEX IF NOT EXISTS idx_memory_sym ON hie_market_memory(symbol, session);
"""


POSTGRES_SCHEMA = """
-- ─── TRADES TABLE ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id                   SERIAL PRIMARY KEY,
    trade_id             VARCHAR(100) UNIQUE NOT NULL,
    mt5_ticket           BIGINT,
    timestamp_open       TIMESTAMPTZ NOT NULL,
    timestamp_close      TIMESTAMPTZ,
    symbol               VARCHAR(20) NOT NULL,
    direction            VARCHAR(5)  NOT NULL,
    entry_price          DECIMAL(12,5) NOT NULL,
    exit_price           DECIMAL(12,5),
    stop_loss            DECIMAL(12,5) NOT NULL,
    take_profit          DECIMAL(12,5) NOT NULL,
    position_size_lots   DECIMAL(8,2) NOT NULL,
    risk_usd             DECIMAL(10,2),
    pnl_usd              DECIMAL(10,2),
    pnl_pct              DECIMAL(8,4),
    risk_reward_ratio    DECIMAL(6,2),
    confidence_score     SMALLINT,
    quality_grade        VARCHAR(5),
    session              VARCHAR(20),
    market_regime        VARCHAR(30),
    strategy_used        VARCHAR(50),
    news_status          BOOLEAN DEFAULT FALSE,
    reason_for_entry     TEXT,
    reason_for_exit      TEXT,
    exit_reason_code     VARCHAR(30),
    be_moved             BOOLEAN DEFAULT FALSE,
    half_closed          BOOLEAN DEFAULT FALSE,
    duration_minutes     INTEGER,
    requested_price      DECIMAL(12,5),
    slippage_points      DECIMAL(12,5),
    entry_spread_points  DECIMAL(12,5),
    execution_latency_ms REAL,
    score_structure      SMALLINT DEFAULT 0,
    score_liquidity      SMALLINT DEFAULT 0,
    score_smc            SMALLINT DEFAULT 0,
    score_trend          SMALLINT DEFAULT 0,
    score_momentum       SMALLINT DEFAULT 0,
    score_volatility     SMALLINT DEFAULT 0,
    score_pullback       SMALLINT DEFAULT 0,
    metadata             TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS rejected_trades (
    id                   SERIAL PRIMARY KEY,
    timestamp            TIMESTAMPTZ NOT NULL,
    symbol               VARCHAR(20) NOT NULL,
    direction            VARCHAR(5),
    confidence_score     SMALLINT,
    failed_conditions    JSONB,
    reason_for_rejection TEXT NOT NULL,
    regime               VARCHAR(30),
    structure_pass       BOOLEAN DEFAULT FALSE,
    liquidity_pass       BOOLEAN DEFAULT FALSE,
    momentum_pass        BOOLEAN DEFAULT FALSE,
    volume_pass          BOOLEAN DEFAULT FALSE,
    metadata             TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS equity_curve (
    id           SERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ NOT NULL,
    equity       DECIMAL(12,2) NOT NULL,
    balance      DECIMAL(12,2),
    open_pnl     DECIMAL(10,2),
    daily_pnl    DECIMAL(10,2),
    weekly_pnl   DECIMAL(10,2),
    monthly_pnl  DECIMAL(10,2)
);

CREATE TABLE IF NOT EXISTS performance_snapshots (
    id               SERIAL PRIMARY KEY,
    period_type      VARCHAR(10) NOT NULL,
    period_start     TIMESTAMPTZ NOT NULL,
    period_end       TIMESTAMPTZ NOT NULL,
    total_trades     INTEGER DEFAULT 0,
    winning_trades   INTEGER DEFAULT 0,
    losing_trades    INTEGER DEFAULT 0,
    win_rate         DECIMAL(5,2),
    profit_factor    DECIMAL(8,2),
    expectancy       DECIMAL(8,2),
    total_pnl        DECIMAL(10,2),
    max_drawdown     DECIMAL(8,4),
    sharpe_ratio     DECIMAL(6,3),
    avg_duration_min INTEGER,
    best_pair        VARCHAR(20),
    worst_pair       VARCHAR(20),
    best_session     VARCHAR(20),
    strategy_data    JSONB
);

CREATE TABLE IF NOT EXISTS system_logs (
    id        SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    level     VARCHAR(10) NOT NULL,
    module    VARCHAR(50),
    message   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol   ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_open     ON trades(timestamp_open);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_used);
CREATE INDEX IF NOT EXISTS idx_trades_session  ON trades(session);
CREATE INDEX IF NOT EXISTS idx_rejected_symbol ON rejected_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_equity_time     ON equity_curve(timestamp);

-- ─── AGENT DECISIONS TABLE ──────────────────────────────
CREATE TABLE IF NOT EXISTS agent_decisions (
    id                   SERIAL PRIMARY KEY,
    timestamp            TIMESTAMPTZ NOT NULL,
    proposal_id          VARCHAR(100) NOT NULL,
    symbol               VARCHAR(20) NOT NULL,
    direction            VARCHAR(5) NOT NULL,
    market_analysis_score SMALLINT,
    news_agent_vote      VARCHAR(10) NOT NULL,          -- APPROVE / VETO
    news_agent_reason    TEXT,
    risk_agent_vote      VARCHAR(10) NOT NULL,          -- APPROVE / VETO
    risk_agent_lots      DECIMAL(8,2),
    risk_agent_reason    TEXT,
    consensus_status     VARCHAR(10) NOT NULL,          -- APPROVED / VETOED
    execution_ticket     BIGINT                 -- Null if vetoed
);

-- ─── CHAT SESSIONS TABLE ────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id           SERIAL PRIMARY KEY,
    session_id   VARCHAR(100) NOT NULL,
    timestamp    TIMESTAMPTZ NOT NULL,
    role         VARCHAR(20) NOT NULL,              -- user / assistant
    message      TEXT NOT NULL,
    intent       VARCHAR(50),                       -- recognized intent if assistant
    parameters   JSONB                              -- JSON map of parsed variables
);

-- ─── LIVE OPPORTUNITIES TABLE ────────────────────────────
CREATE TABLE IF NOT EXISTS live_opportunities (
    id                   SERIAL PRIMARY KEY,
    symbol               VARCHAR(20) NOT NULL,
    strategy             VARCHAR(100) NOT NULL,
    confidence_score     INTEGER NOT NULL,
    direction            VARCHAR(5) NOT NULL,
    entry_price          DECIMAL(12,5) NOT NULL,
    stop_loss            DECIMAL(12,5) NOT NULL,
    take_profit          DECIMAL(12,5) NOT NULL,
    reasons              TEXT,
    registered_at        TIMESTAMPTZ NOT NULL
);

-- ─── CORRELATION MATRIX CACHE TABLE ──────────────────────
CREATE TABLE IF NOT EXISTS correlation_matrix_cache (
    id                   SERIAL PRIMARY KEY,
    matrix_json          TEXT NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_prop ON agent_decisions(proposal_id);
CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_live_opp_score ON live_opportunities(confidence_score);

-- ─── EXTENDED TABLES FOR INSTITUTIONAL COMMAND CENTER ───
CREATE TABLE IF NOT EXISTS trade_journal (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    confluence_matrix TEXT,
    post_mortem_notes TEXT,
    ai_coach_verdict TEXT,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
);
CREATE TABLE IF NOT EXISTS trade_rejections (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(5),
    confidence_score INTEGER,
    reason_for_rejection TEXT NOT NULL,
    failed_conditions TEXT,
    market_regime VARCHAR(30),
    indicator_states TEXT
);
CREATE TABLE IF NOT EXISTS symbol_statistics (
    symbol VARCHAR(20) PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    avg_win DECIMAL(12,2) DEFAULT 0.0,
    avg_loss DECIMAL(12,2) DEFAULT 0.0,
    avg_quality_score DECIMAL(5,2) DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS strategy_statistics (
    strategy VARCHAR(100) PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    avg_hold_time DECIMAL(8,2) DEFAULT 0.0,
    avg_rr DECIMAL(6,2) DEFAULT 0.0,
    expected_value DECIMAL(8,2) DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS market_conditions (
    id SERIAL PRIMARY KEY,
    regime VARCHAR(50) UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    best_strategy VARCHAR(100),
    worst_strategy VARCHAR(100),
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS opportunity_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    strategy VARCHAR(100) NOT NULL,
    direction VARCHAR(5) NOT NULL,
    confidence_score INTEGER NOT NULL,
    status VARCHAR(30) NOT NULL,
    decision_reason TEXT
);
CREATE TABLE IF NOT EXISTS signal_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    indicator_name VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(12,5) NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_metrics (
    id SERIAL PRIMARY KEY,
    trade_id VARCHAR(100) UNIQUE NOT NULL,
    execution_delay_ms INTEGER,
    latency_ms INTEGER,
    spread_at_entry DECIMAL(8,2),
    spread_at_exit DECIMAL(8,2),
    slippage_points DECIMAL(8,2),
    partial_fills INTEGER DEFAULT 0,
    order_rejections INTEGER DEFAULT 0,
    broker_response_time_ms INTEGER
);
CREATE TABLE IF NOT EXISTS broker_metrics (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    broker_name VARCHAR(100) NOT NULL,
    execution_speed_ms INTEGER,
    spread_history TEXT,
    spread_spikes INTEGER DEFAULT 0,
    connection_stability DECIMAL(5,2) DEFAULT 100.0,
    order_fill_quality DECIMAL(5,2) DEFAULT 100.0
);
CREATE TABLE IF NOT EXISTS decision_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    trade_id VARCHAR(100),
    action VARCHAR(20) NOT NULL,
    decision_matrix TEXT NOT NULL,
    memory_context_ids TEXT
);
CREATE TABLE IF NOT EXISTS decision_memory (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    memory_type VARCHAR(30) NOT NULL,
    summary_text TEXT NOT NULL,
    confidence_delta DECIMAL(5,2) DEFAULT 0.0,
    associated_trades TEXT
);
CREATE TABLE IF NOT EXISTS market_memory (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(12,5) NOT NULL,
    market_regime VARCHAR(30) NOT NULL,
    volatility_atr DECIMAL(8,4),
    bid_ask_spread DECIMAL(8,4)
);
CREATE TABLE IF NOT EXISTS learning_recommendations (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    category VARCHAR(30) NOT NULL,
    recommendation_text TEXT NOT NULL,
    supporting_evidence TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    applied INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pattern_discoveries (
    id SERIAL PRIMARY KEY,
    pattern_signature VARCHAR(100) UNIQUE NOT NULL,
    confluences TEXT NOT NULL,
    occurrences INTEGER DEFAULT 0,
    success_rate DECIMAL(5,2) DEFAULT 0.0,
    avg_pnl DECIMAL(12,2) DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS failure_patterns (
    id SERIAL PRIMARY KEY,
    failure_signature VARCHAR(100) UNIQUE NOT NULL,
    confluences TEXT NOT NULL,
    occurrences INTEGER DEFAULT 0,
    fail_rate DECIMAL(5,2) DEFAULT 0.0,
    avg_loss DECIMAL(12,2) DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS system_health (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    cpu_usage DECIMAL(5,2),
    ram_usage DECIMAL(5,2),
    disk_usage DECIMAL(5,2),
    db_health_status VARCHAR(20),
    mt5_connection_status VARCHAR(20),
    api_health_status VARCHAR(20)
);
CREATE TABLE IF NOT EXISTS module_health (
    module_name VARCHAR(100) PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    latency_ms DECIMAL(8,2),
    last_activity TIMESTAMPTZ NOT NULL,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS portfolio_exposure (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    sector_exposures TEXT NOT NULL,
    currency_stack TEXT NOT NULL,
    margin_used DECIMAL(12,2),
    free_margin DECIMAL(12,2),
    margin_level DECIMAL(8,2),
    leverage_utilization DECIMAL(8,2)
);
CREATE TABLE IF NOT EXISTS risk_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    description TEXT NOT NULL,
    action_taken VARCHAR(50) NOT NULL
);
CREATE TABLE IF NOT EXISTS trade_playbacks (
    trade_id VARCHAR(100) PRIMARY KEY,
    candles_history TEXT NOT NULL,
    indicator_history TEXT NOT NULL,
    decision_timeline TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
);
CREATE TABLE IF NOT EXISTS session_analytics (
    session_name VARCHAR(20) PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    avg_score DECIMAL(5,2) DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS timeframe_analytics (
    timeframe VARCHAR(10) PRIMARY KEY,
    total_trades INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    signal_quality DECIMAL(5,2) DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS strategy_evolution_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    parameter_updates TEXT NOT NULL,
    optimizer_run_id VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS daily_reports (
    id SERIAL PRIMARY KEY,
    report_date VARCHAR(20) UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS weekly_reports (
    id SERIAL PRIMARY KEY,
    week_start VARCHAR(20) UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    summary TEXT
);
CREATE TABLE IF NOT EXISTS monthly_reports (
    id SERIAL PRIMARY KEY,
    month_start VARCHAR(20) UNIQUE NOT NULL,
    total_trades INTEGER DEFAULT 0,
    net_pnl DECIMAL(12,2) DEFAULT 0.0,
    win_rate DECIMAL(5,2) DEFAULT 0.0,
    profit_factor DECIMAL(8,2) DEFAULT 0.0,
    summary TEXT
);

-- ─── HIE TABLES ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hie_candles (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    timeframe   VARCHAR(10) NOT NULL,
    timestamp   VARCHAR(30) NOT NULL,
    open        DOUBLE PRECISION NOT NULL,
    high        DOUBLE PRECISION NOT NULL,
    low         DOUBLE PRECISION NOT NULL,
    close       DOUBLE PRECISION NOT NULL,
    volume      DOUBLE PRECISION DEFAULT 0,
    spread      DOUBLE PRECISION DEFAULT 0,
    UNIQUE(symbol, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS hie_setups (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    timeframe   VARCHAR(10) NOT NULL,
    setup_type  VARCHAR(50) NOT NULL,
    direction   VARCHAR(5) NOT NULL,
    session     VARCHAR(20) NOT NULL,
    timestamp   VARCHAR(30) NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    stop_loss   DOUBLE PRECISION NOT NULL,
    take_profit DOUBLE PRECISION NOT NULL,
    atr         DOUBLE PRECISION DEFAULT 0,
    outcome_analyzed INTEGER DEFAULT 0,
    UNIQUE(symbol, timeframe, setup_type, direction, timestamp)
);

CREATE TABLE IF NOT EXISTS hie_setup_outcomes (
    id           SERIAL PRIMARY KEY,
    setup_id     INTEGER NOT NULL UNIQUE,
    symbol       VARCHAR(20) NOT NULL,
    timeframe    VARCHAR(10) NOT NULL,
    setup_type   VARCHAR(50) NOT NULL,
    direction    VARCHAR(5) NOT NULL,
    session      VARCHAR(20) NOT NULL,
    timestamp    VARCHAR(30) NOT NULL,
    entry_price  DOUBLE PRECISION NOT NULL,
    stop_loss    DOUBLE PRECISION NOT NULL,
    take_profit  DOUBLE PRECISION NOT NULL,
    risk_r       DOUBLE PRECISION NOT NULL,
    reached_0_5r INTEGER DEFAULT 0,
    reached_1r   INTEGER DEFAULT 0,
    reached_2r   INTEGER DEFAULT 0,
    reached_3r   INTEGER DEFAULT 0,
    reached_5r   INTEGER DEFAULT 0,
    is_win       INTEGER DEFAULT 0,
    pnl_r        DOUBLE PRECISION DEFAULT 0,
    mfe_r        DOUBLE PRECISION DEFAULT 0,
    mae_r        DOUBLE PRECISION DEFAULT 0,
    bars_held    INTEGER DEFAULT 0,
    FOREIGN KEY(setup_id) REFERENCES hie_setups(id)
);

CREATE TABLE IF NOT EXISTS hie_pattern_stats (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20) NOT NULL,
    setup_type   VARCHAR(50) NOT NULL,
    direction    VARCHAR(5) NOT NULL,
    session      VARCHAR(20) NOT NULL,
    timeframe    VARCHAR(10) NOT NULL,
    occurrences  INTEGER DEFAULT 0,
    wins         INTEGER DEFAULT 0,
    losses       INTEGER DEFAULT 0,
    win_rate     DOUBLE PRECISION DEFAULT 0,
    avg_rr       DOUBLE PRECISION DEFAULT 0,
    avg_mfe_r    DOUBLE PRECISION DEFAULT 0,
    avg_mae_r    DOUBLE PRECISION DEFAULT 0,
    reach_1r_pct DOUBLE PRECISION DEFAULT 0,
    reach_2r_pct DOUBLE PRECISION DEFAULT 0,
    reach_3r_pct DOUBLE PRECISION DEFAULT 0,
    updated_at   VARCHAR(30) NOT NULL,
    UNIQUE(symbol, setup_type, direction, session, timeframe)
);

CREATE TABLE IF NOT EXISTS hie_market_memory (
    id           SERIAL PRIMARY KEY,
    symbol       VARCHAR(20) NOT NULL,
    setup_type   VARCHAR(50) NOT NULL,
    session      VARCHAR(20) NOT NULL,
    direction    VARCHAR(5) NOT NULL,
    occurrences  INTEGER DEFAULT 0,
    win_rate     DOUBLE PRECISION DEFAULT 0,
    avg_rr       DOUBLE PRECISION DEFAULT 0,
    memory_label TEXT,
    is_strong    INTEGER DEFAULT 0,
    is_weak      INTEGER DEFAULT 0,
    updated_at   VARCHAR(30) NOT NULL,
    UNIQUE(symbol, setup_type, session, direction)
);

CREATE TABLE IF NOT EXISTS hie_symbol_profiles (
    symbol           VARCHAR(20) PRIMARY KEY,
    best_session     VARCHAR(20),
    worst_session    VARCHAR(20),
    best_timeframe   VARCHAR(10),
    worst_timeframe  VARCHAR(10),
    best_setup       VARCHAR(50),
    worst_setup      VARCHAR(50),
    overall_win_rate DOUBLE PRECISION DEFAULT 0,
    overall_avg_rr   DOUBLE PRECISION DEFAULT 0,
    profile_json     TEXT,
    updated_at       VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS hie_confidence_calibration (
    id           SERIAL PRIMARY KEY,
    score_bucket VARCHAR(20) NOT NULL UNIQUE,
    sample_size  INTEGER DEFAULT 0,
    actual_wins  INTEGER DEFAULT 0,
    actual_wr    DOUBLE PRECISION DEFAULT 0,
    expected_wr  DOUBLE PRECISION DEFAULT 0,
    calibrated_at VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS hie_similarity_cache (
    id           SERIAL PRIMARY KEY,
    query_hash   VARCHAR(64) UNIQUE NOT NULL,
    result_json  TEXT NOT NULL,
    cached_at    VARCHAR(30) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hie_candles_sym_tf_ts ON hie_candles(symbol, timeframe, timestamp);
CREATE INDEX IF NOT EXISTS idx_hie_setups_sym ON hie_setups(symbol, timeframe, setup_type);
CREATE INDEX IF NOT EXISTS idx_hie_setups_session ON hie_setups(session);
CREATE INDEX IF NOT EXISTS idx_outcome_sym ON hie_setup_outcomes(symbol, setup_type, session);
CREATE INDEX IF NOT EXISTS idx_hie_pstats_sym ON hie_pattern_stats(symbol, setup_type);
CREATE INDEX IF NOT EXISTS idx_hie_pstats_sess ON hie_pattern_stats(session);
CREATE INDEX IF NOT EXISTS idx_memory_sym ON hie_market_memory(symbol, session);
"""


# ════════════════════════════════════════════════
#  DATABASE CLASS
# ════════════════════════════════════════════════

class ZohraDatabase:
    """
    Unified database layer.
    Auto-selects PostgreSQL (if configured) or SQLite.
    All public methods work identically regardless of backend.
    """

    def __init__(self):
        self._use_postgres = USE_POSTGRES and PSYCOPG2_AVAILABLE
        self._sqlite_conn  = None
        self._pg_config    = None

        if self._use_postgres:
            self._pg_config = {
                "host":     POSTGRES_HOST,
                "port":     POSTGRES_PORT,
                "dbname":   POSTGRES_DB,
                "user":     POSTGRES_USER,
                "password": POSTGRES_PASSWORD,
            }
            logger.info(f"📦 Database: PostgreSQL @ {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
            self._init_postgres()
        else:
            _db_path = DB_PATH
            try:
                os.makedirs(os.path.dirname(os.path.abspath(_db_path)), exist_ok=True)
            except OSError:
                # Read-only deployment filesystem (e.g. Vercel) - fall back to /tmp
                _db_path = "/tmp/zohra_trades.db"
            self._sqlite_conn = sqlite3.connect(_db_path, check_same_thread=False, timeout=30.0)
            self._sqlite_conn.row_factory = sqlite3.Row
            logger.info(f"📦 Database: SQLite @ {_db_path}")
            self._init_sqlite()

    # ─── Init ─────────────────────────────────────────────
    def _init_sqlite(self):
        try:
            self._sqlite_conn.execute("PRAGMA journal_mode=WAL;")
            self._sqlite_conn.execute("PRAGMA synchronous=NORMAL;")
        except Exception as e:
            logger.warning(f"Failed to set WAL mode: {e}")
        self._sqlite_conn.executescript(SQLITE_SCHEMA)
        self._sqlite_conn.commit()
        
        # SQLite migrations for existing databases
        cursor = self._sqlite_conn.cursor()
        
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if "metadata" not in columns:
            logger.info("Migrating SQLite trades table: Adding metadata column")
            cursor.execute("ALTER TABLE trades ADD COLUMN metadata TEXT DEFAULT '{}'")
            self._sqlite_conn.commit()
            
        for col in ["requested_price", "slippage_points", "entry_spread_points", "execution_latency_ms"]:
            if col not in columns:
                logger.info(f"Migrating SQLite trades table: Adding {col} column")
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} REAL")
                self._sqlite_conn.commit()
            
        cursor.execute("PRAGMA table_info(rejected_trades)")
        columns = [row[1] for row in cursor.fetchall()]
        if "metadata" not in columns:
            logger.info("Migrating SQLite rejected_trades table: Adding metadata column")
            cursor.execute("ALTER TABLE rejected_trades ADD COLUMN metadata TEXT DEFAULT '{}'")
            self._sqlite_conn.commit()

        cursor.execute("PRAGMA table_info(learning_recommendations)")
        rec_columns = [row[1] for row in cursor.fetchall()]
        if "applied" not in rec_columns:
            logger.info("Migrating SQLite learning_recommendations table: Adding applied column")
            cursor.execute("ALTER TABLE learning_recommendations ADD COLUMN applied INTEGER DEFAULT 0")
            self._sqlite_conn.commit()
        if "is_active" not in rec_columns:
            logger.info("Migrating SQLite learning_recommendations table: Adding is_active column")
            cursor.execute("ALTER TABLE learning_recommendations ADD COLUMN is_active INTEGER DEFAULT 1")
            self._sqlite_conn.commit()

    def _init_postgres(self):
        with self._pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(POSTGRES_SCHEMA)
                
                # Check and add metadata column to trades if not exists
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='trades' AND column_name='metadata'
                """)
                if not cur.fetchone():
                    logger.info("Migrating Postgres trades table: Adding metadata column")
                    cur.execute("ALTER TABLE trades ADD COLUMN metadata TEXT DEFAULT '{}'")

                for col in ["requested_price", "slippage_points", "entry_spread_points", "execution_latency_ms"]:
                    cur.execute(f"""
                        SELECT column_name FROM information_schema.columns 
                        WHERE table_name='trades' AND column_name='{col}'
                    """)
                    if not cur.fetchone():
                        logger.info(f"Migrating Postgres trades table: Adding {col} column")
                        col_type = "REAL"
                        if col in ["requested_price", "slippage_points", "entry_spread_points"]:
                            col_type = "DECIMAL(12,5)"
                        cur.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
                    
                # Check and add metadata column to rejected_trades if not exists
                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='rejected_trades' AND column_name='metadata'
                """)
                if not cur.fetchone():
                    logger.info("Migrating Postgres rejected_trades table: Adding metadata column")
                    cur.execute("ALTER TABLE rejected_trades ADD COLUMN metadata TEXT DEFAULT '{}'")

                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='learning_recommendations' AND column_name='applied'
                """)
                if not cur.fetchone():
                    logger.info("Migrating Postgres learning_recommendations table: Adding applied column")
                    cur.execute("ALTER TABLE learning_recommendations ADD COLUMN applied INTEGER DEFAULT 0")

                cur.execute("""
                    SELECT column_name FROM information_schema.columns 
                    WHERE table_name='learning_recommendations' AND column_name='is_active'
                """)
                if not cur.fetchone():
                    logger.info("Migrating Postgres learning_recommendations table: Adding is_active column")
                    cur.execute("ALTER TABLE learning_recommendations ADD COLUMN is_active INTEGER DEFAULT 1")
            conn.commit()

    @contextmanager
    def _pg_conn(self):
        conn = psycopg2.connect(**self._pg_config)
        try:
            yield conn
        finally:
            conn.close()

    def _execute(self, sql: str, params: tuple = (), fetch: str = None) -> Any:
        """Unified execute for both backends."""
        if self._use_postgres:
            with self._pg_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql.replace("?", "%s"), params)
                    conn.commit()
                    if fetch == "one":
                        return cur.fetchone()
                    if fetch == "all":
                        return cur.fetchall()
        else:
            cur = self._sqlite_conn.cursor()
            cur.execute(sql, params)
            self._sqlite_conn.commit()
            if fetch == "one":
                row = cur.fetchone()
                return dict(row) if row else None
            if fetch == "all":
                rows = cur.fetchall()
                return [dict(r) for r in rows]

    # ────────────────────────────────────────────────────────
    #  TRADE LOGGING
    # ────────────────────────────────────────────────────────

    def log_trade_open(self, trade: Dict) -> bool:
        """
        Log a new trade when it opens.
        Required keys: trade_id, symbol, direction, entry_price,
                       stop_loss, take_profit, position_size_lots
        Optional: mt5_ticket, confidence_score, quality_grade,
                  session, market_regime, strategy_used, reason_for_entry,
                  score_structure, score_liquidity, score_smc, score_trend,
                  score_momentum, score_volatility, score_pullback
        """
        try:
            self._execute("""
                INSERT INTO trades (
                    trade_id, mt5_ticket, timestamp_open, symbol, direction,
                    entry_price, stop_loss, take_profit, position_size_lots,
                    risk_usd, confidence_score, quality_grade, session,
                    market_regime, strategy_used, news_status, reason_for_entry,
                    score_structure, score_liquidity, score_smc, score_trend,
                    score_momentum, score_volatility, score_pullback,
                    requested_price, slippage_points, entry_spread_points, execution_latency_ms,
                    metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade.get('trade_id'),
                trade.get('mt5_ticket'),
                datetime.utcnow().isoformat(),
                trade.get('symbol'),
                trade.get('direction'),
                trade.get('entry_price'),
                trade.get('stop_loss'),
                trade.get('take_profit'),
                trade.get('position_size_lots', trade.get('lots', 0.01)),
                trade.get('risk_usd', 0.0),
                trade.get('confidence_score', trade.get('score', 0)),
                trade.get('quality_grade', trade.get('quality', '')),
                trade.get('session', ''),
                trade.get('market_regime', trade.get('regime', '')),
                trade.get('strategy_used', 'SMC'),
                int(trade.get('news_status', False)),
                trade.get('reason_for_entry', ''),
                trade.get('score_structure', 0),
                trade.get('score_liquidity', 0),
                trade.get('score_smc', 0),
                trade.get('score_trend', 0),
                trade.get('score_momentum', 0),
                trade.get('score_volatility', 0),
                trade.get('score_pullback', 0),
                trade.get('requested_price'),
                trade.get('slippage_points'),
                trade.get('entry_spread_points'),
                trade.get('execution_latency_ms'),
                trade.get('metadata', '{}')
            ))
            logger.info(f"📝 Trade opened: {trade.get('trade_id')} — {trade.get('symbol')} {trade.get('direction')}")
            return True
        except Exception as e:
            logger.error(f"❌ log_trade_open error: {e}")
            return False

    def log_trade_close(self, trade_id: str, exit_price: float, pnl_usd: float,
                        pnl_pct: float, exit_reason: str, exit_code: str = "",
                        duration_minutes: int = 0) -> bool:
        """Update trade record on close with full P&L data."""
        try:
            self._execute("""
                UPDATE trades SET
                    timestamp_close  = ?,
                    exit_price       = ?,
                    pnl_usd          = ?,
                    pnl_pct          = ?,
                    reason_for_exit  = ?,
                    exit_reason_code = ?,
                    duration_minutes = ?,
                    risk_reward_ratio = CASE
                        WHEN risk_usd > 0 THEN ABS(? / risk_usd)
                        ELSE 0
                    END
                WHERE trade_id = ?
            """, (
                datetime.utcnow().isoformat(),
                exit_price, pnl_usd, pnl_pct,
                exit_reason, exit_code, duration_minutes,
                pnl_usd,
                trade_id
            ))
            emoji = "✅" if pnl_usd >= 0 else "❌"
            logger.info(f"{emoji} Trade closed: {trade_id} | P&L: ${pnl_usd:.2f}")
            return True
        except Exception as e:
            logger.error(f"❌ log_trade_close error: {e}")
            return False

    # ────────────────────────────────────────────────────────
    #  REJECTED TRADE LOGGING
    # ────────────────────────────────────────────────────────

    def log_rejection(self, rejection: Dict) -> bool:
        """
        Log every rejected trade opportunity.
        Required: symbol, reason_for_rejection
        Optional: direction, confidence_score, failed_conditions (list),
                  regime, structure_pass, liquidity_pass, momentum_pass, volume_pass
        """
        try:
            failed = rejection.get('failed_conditions', [])
            failed_json = json.dumps(failed) if isinstance(failed, list) else str(failed)

            self._execute("""
                INSERT INTO rejected_trades (
                    timestamp, symbol, direction, confidence_score,
                    failed_conditions, reason_for_rejection, regime,
                    structure_pass, liquidity_pass, momentum_pass, volume_pass
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                datetime.utcnow().isoformat(),
                rejection.get('symbol', ''),
                rejection.get('direction', ''),
                rejection.get('confidence_score', rejection.get('score', 0)),
                failed_json,
                rejection.get('reason_for_rejection', rejection.get('reason', '')),
                rejection.get('regime', ''),
                int(rejection.get('structure_pass', False)),
                int(rejection.get('liquidity_pass', False)),
                int(rejection.get('momentum_pass', False)),
                int(rejection.get('volume_pass', False)),
            ))
            return True
        except Exception as e:
            logger.error(f"❌ log_rejection error: {e}")
            return False

    # ────────────────────────────────────────────────────────
    #  AGENT DECISIONS LOGGING
    # ────────────────────────────────────────────────────────

    def log_agent_decision(self, decision: Dict) -> bool:
        """
        Log an agent consensus decision (approval or veto).
        Required: proposal_id, symbol, direction, news_agent_vote, risk_agent_vote, consensus_status
        Optional: market_analysis_score, news_agent_reason, risk_agent_lots, risk_agent_reason, execution_ticket
        """
        try:
            self._execute("""
                INSERT INTO agent_decisions (
                    timestamp, proposal_id, symbol, direction, market_analysis_score,
                    news_agent_vote, news_agent_reason, risk_agent_vote,
                    risk_agent_lots, risk_agent_reason, consensus_status, execution_ticket
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().isoformat(),
                decision.get('proposal_id'),
                decision.get('symbol'),
                decision.get('direction'),
                decision.get('market_analysis_score'),
                decision.get('news_agent_vote'),
                decision.get('news_agent_reason'),
                decision.get('risk_agent_vote'),
                decision.get('risk_agent_lots'),
                decision.get('risk_agent_reason'),
                decision.get('consensus_status'),
                decision.get('execution_ticket')
            ))
            return True
        except Exception as e:
            logger.error(f"❌ log_agent_decision error: {e}")
            return False

    # ────────────────────────────────────────────────────────
    #  EQUITY CURVE
    # ────────────────────────────────────────────────────────

    def log_equity(self, equity: float, balance: float = 0.0,
                   open_pnl: float = 0.0, daily_pnl: float = 0.0,
                   weekly_pnl: float = 0.0, monthly_pnl: float = 0.0) -> bool:
        try:
            self._execute("""
                INSERT INTO equity_curve
                    (timestamp, equity, balance, open_pnl, daily_pnl, weekly_pnl, monthly_pnl)
                VALUES (?,?,?,?,?,?,?)
            """, (datetime.utcnow().isoformat(), equity, balance,
                  open_pnl, daily_pnl, weekly_pnl, monthly_pnl))
            return True
        except Exception as e:
            logger.error(f"❌ log_equity error: {e}")
            return False

    # ────────────────────────────────────────────────────────
    #  PERFORMANCE SNAPSHOT
    # ────────────────────────────────────────────────────────

    def save_performance_snapshot(self, snapshot: Dict) -> bool:
        """Save daily/weekly/monthly performance snapshot."""
        try:
            self._execute("""
                INSERT INTO performance_snapshots (
                    period_type, period_start, period_end,
                    total_trades, winning_trades, losing_trades,
                    win_rate, profit_factor, expectancy, total_pnl,
                    max_drawdown, sharpe_ratio, avg_duration_min,
                    best_pair, worst_pair, best_session, strategy_data
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                snapshot.get('period_type'),
                snapshot.get('period_start'),
                snapshot.get('period_end'),
                snapshot.get('total_trades', 0),
                snapshot.get('winning_trades', 0),
                snapshot.get('losing_trades', 0),
                snapshot.get('win_rate', 0.0),
                snapshot.get('profit_factor', 0.0),
                snapshot.get('expectancy', 0.0),
                snapshot.get('total_pnl', 0.0),
                snapshot.get('max_drawdown', 0.0),
                snapshot.get('sharpe_ratio', 0.0),
                snapshot.get('avg_duration_min', 0),
                snapshot.get('best_pair', ''),
                snapshot.get('worst_pair', ''),
                snapshot.get('best_session', ''),
                json.dumps(snapshot.get('strategy_data', {})),
            ))
            return True
        except Exception as e:
            logger.error(f"❌ save_performance_snapshot error: {e}")
            return False

    # ────────────────────────────────────────────────────────
    #  SYSTEM LOGGING
    # ────────────────────────────────────────────────────────

    def log_system(self, level: str, message: str, module: str = "Engine") -> None:
        try:
            self._execute("""
                INSERT INTO system_logs (timestamp, level, module, message)
                VALUES (?,?,?,?)
            """, (datetime.utcnow().isoformat(), level.upper(), module, message))
        except Exception as e:
            logger.error(f"❌ log_system error: {e}")

    # ────────────────────────────────────────────────────────
    #  QUERIES
    # ────────────────────────────────────────────────────────

    def get_open_trades(self) -> List[Dict]:
        return self._execute(
            "SELECT * FROM trades WHERE timestamp_close IS NULL ORDER BY timestamp_open DESC",
            fetch="all"
        ) or []

    def get_closed_trades(self, limit: int = 100, symbol: str = None,
                          days: int = None) -> List[Dict]:
        conditions = ["timestamp_close IS NOT NULL"]
        params = []
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if days:
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            conditions.append("timestamp_close >= ?")
            params.append(since)
        where = " AND ".join(conditions)
        params.append(limit)
        return self._execute(
            f"SELECT * FROM trades WHERE {where} ORDER BY timestamp_close DESC LIMIT ?",
            tuple(params), fetch="all"
        ) or []

    def get_rejections(self, limit: int = 50, symbol: str = None) -> List[Dict]:
        if symbol:
            return self._execute(
                "SELECT * FROM rejected_trades WHERE symbol=? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit), fetch="all"
            ) or []
        return self._execute(
            "SELECT * FROM rejected_trades ORDER BY timestamp DESC LIMIT ?",
            (limit,), fetch="all"
        ) or []

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._execute(
            "SELECT * FROM equity_curve WHERE timestamp >= ? ORDER BY timestamp",
            (since,), fetch="all"
        ) or []

    def get_raw_stats(self, days: int = None) -> Dict:
        """Raw aggregate stats for analytics engine to process."""
        conditions = ["timestamp_close IS NOT NULL"]
        params = []
        if days:
            since = (datetime.utcnow() - timedelta(days=days)).isoformat()
            conditions.append("timestamp_close >= ?")
            params.append(since)
        where = " AND ".join(conditions)

        total_row = self._execute(
            f"SELECT COUNT(*) as cnt FROM trades WHERE {where}", tuple(params), fetch="one"
        )
        total = (total_row or {}).get('cnt', 0)

        wins_row = self._execute(
            f"SELECT COUNT(*) as cnt FROM trades WHERE {where} AND pnl_usd > 0",
            tuple(params), fetch="one"
        )
        wins = (wins_row or {}).get('cnt', 0)

        agg = self._execute(
            f"""SELECT
                SUM(pnl_usd)       AS total_pnl,
                AVG(pnl_usd)       AS avg_pnl,
                AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END) AS avg_win,
                AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END) AS avg_loss,
                SUM(CASE WHEN pnl_usd > 0 THEN pnl_usd ELSE 0 END) AS gross_profit,
                SUM(CASE WHEN pnl_usd < 0 THEN ABS(pnl_usd) ELSE 0 END) AS gross_loss,
                AVG(duration_minutes) AS avg_duration,
                AVG(risk_reward_ratio) AS avg_rr
            FROM trades WHERE {where}""",
            tuple(params), fetch="one"
        ) or {}

        return {
            "total_trades": total,
            "wins": wins,
            "losses": total - wins,
            "total_pnl": float(agg.get("total_pnl") or 0),
            "avg_pnl": float(agg.get("avg_pnl") or 0),
            "avg_win": float(agg.get("avg_win") or 0),
            "avg_loss": float(agg.get("avg_loss") or 0),
            "gross_profit": float(agg.get("gross_profit") or 0),
            "gross_loss": float(agg.get("gross_loss") or 0),
            "avg_duration_min": float(agg.get("avg_duration") or 0),
            "avg_rr": float(agg.get("avg_rr") or 0),
        }

    def get_session_stats(self, days: int = 30) -> List[Dict]:
        """Performance broken down by session."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._execute("""
            SELECT
                session,
                COUNT(*) AS total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(pnl_usd) AS total_pnl,
                AVG(pnl_usd) AS avg_pnl
            FROM trades
            WHERE timestamp_close IS NOT NULL
              AND timestamp_close >= ?
            GROUP BY session
            ORDER BY total_pnl DESC
        """, (since,), fetch="all") or []

    def get_pair_stats(self, days: int = 30) -> List[Dict]:
        """Performance broken down by symbol."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._execute("""
            SELECT
                symbol,
                COUNT(*) AS total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(pnl_usd) AS total_pnl,
                AVG(pnl_usd) AS avg_pnl,
                AVG(risk_reward_ratio) AS avg_rr
            FROM trades
            WHERE timestamp_close IS NOT NULL
              AND timestamp_close >= ?
            GROUP BY symbol
            ORDER BY total_pnl DESC
        """, (since,), fetch="all") or []

    def get_strategy_stats(self, days: int = 30) -> List[Dict]:
        """Performance broken down by strategy."""
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return self._execute("""
            SELECT
                strategy_used,
                COUNT(*) AS total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) AS wins,
                SUM(pnl_usd) AS total_pnl,
                AVG(pnl_usd) AS avg_pnl,
                AVG(confidence_score) AS avg_score
            FROM trades
            WHERE timestamp_close IS NOT NULL
              AND timestamp_close >= ?
            GROUP BY strategy_used
            ORDER BY total_pnl DESC
        """, (since,), fetch="all") or []

    def log_chat_message(self, session_id: str, role: str, message: str,
                         intent: str = None, parameters: dict = None) -> bool:
        """Log a chat message to session history."""
        try:
            params_str = json.dumps(parameters) if parameters is not None else None
            self._execute("""
                INSERT INTO chat_sessions (session_id, timestamp, role, message, intent, parameters)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session_id,
                datetime.utcnow().isoformat(),
                role,
                message,
                intent,
                params_str
            ))
            return True
        except Exception as e:
            logger.error(f"❌ log_chat_message error: {e}")
            return False

    def get_chat_history(self, session_id: str, limit: int = 50) -> List[Dict]:
        """Fetch message history for a given session ID."""
        try:
            rows = self._execute("""
                SELECT timestamp, role, message, intent, parameters
                FROM chat_sessions
                WHERE session_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
            """, (session_id, limit), fetch="all") or []
            
            for r in rows:
                if r.get('parameters'):
                    try:
                        if isinstance(r['parameters'], str):
                            r['parameters'] = json.loads(r['parameters'])
                    except Exception:
                        pass
            return rows
        except Exception as e:
            logger.error(f"❌ get_chat_history error: {e}")
            return []

    def save_live_opportunities(self, opportunities: List[Dict]):
        """Persists the live ranked setups to database."""
        try:
            self._execute("DELETE FROM live_opportunities")
            for opp in opportunities:
                self._execute("""
                    INSERT INTO live_opportunities (
                        symbol, strategy, confidence_score, direction,
                        entry_price, stop_loss, take_profit, reasons, registered_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    opp["symbol"], opp["strategy"], int(opp["confidence_score"]), opp["direction"],
                    float(opp["entry_price"]), float(opp["stop_loss"]), float(opp["take_profit"]),
                    json.dumps(opp.get("reasons", [])), opp.get("timestamp")
                ))
        except Exception as e:
            logger.error(f"❌ save_live_opportunities error: {e}")

    def get_live_opportunities(self) -> List[Dict]:
        """Loads and returns all live opportunities from the database."""
        try:
            rows = self._execute("""
                SELECT symbol, strategy, confidence_score, direction, entry_price, stop_loss, take_profit, reasons, registered_at
                FROM live_opportunities
                ORDER BY confidence_score DESC
            """, fetch="all") or []
            
            opps = []
            for r in rows:
                opps.append({
                    "symbol": r["symbol"],
                    "strategy": r["strategy"],
                    "confidence_score": r["confidence_score"],
                    "direction": r["direction"],
                    "entry_price": r["entry_price"],
                    "stop_loss": r["stop_loss"],
                    "take_profit": r["take_profit"],
                    "reasons": json.loads(r["reasons"]) if isinstance(r.get("reasons"), str) else (r.get("reasons") or []),
                    "timestamp": r.get("registered_at")
                })
            return opps
        except Exception as e:
            logger.error(f"❌ get_live_opportunities error: {e}")
            return []

    def close(self):
        if self._sqlite_conn:
            self._sqlite_conn.close()


# ════════════════════════════════════════════════
#  SINGLETON
# ════════════════════════════════════════════════
try:
    os.makedirs(LOG_DIR, exist_ok=True)
except OSError:
    pass  # read-only deployment filesystem (e.g. Vercel) - paths fall back to /tmp
db = ZohraDatabase()
