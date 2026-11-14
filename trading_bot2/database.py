"""
SQLite database for trade logging and performance tracking.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict
from config import DB_PATH

class TradeDatabase:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._init_tables()

    def _init_tables(self):
        """Create tables if not exist"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                timestamp_open TEXT,
                timestamp_close TEXT,
                symbol TEXT,
                direction TEXT,
                entry_price REAL,
                exit_price REAL,
                stop_price REAL,
                target_price REAL,
                position_size INTEGER,
                risk_usd REAL,
                pnl_usd REAL,
                pnl_pct REAL,
                exit_reason TEXT,
                ema_fast REAL,
                ema_slow REAL,
                atr REAL,
                mt5_ticket TEXT
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                signal TEXT,
                price REAL,
                ema_fast REAL,
                ema_slow REAL,
                atr REAL,
                executed BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS equity_curve (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                equity REAL,
                open_pnl REAL,
                daily_pnl REAL,
                monthly_pnl REAL
            );

            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                message TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_open ON trades(timestamp_open);
            CREATE INDEX IF NOT EXISTS idx_equity_time ON equity_curve(timestamp);
        """)
        self.conn.commit()

    def log_trade(self, trade: Dict):
        """Log a new trade"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO trades (
                trade_id, timestamp_open, symbol, direction,
                entry_price, stop_price, target_price, position_size,
                risk_usd, ema_fast, ema_slow, atr, mt5_ticket
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade['trade_id'], trade['timestamp_open'], trade['symbol'],
            trade['direction'], trade['entry_price'], trade['stop_price'],
            trade['target_price'], trade['position_size'], trade['risk_usd'],
            trade['ema_fast'], trade['ema_slow'], trade['atr'], trade.get('mt5_ticket')
        ))
        self.conn.commit()

    def close_trade(self, trade_id: str, exit_price: float, pnl_usd: float,
                    pnl_pct: float, exit_reason: str, mt5_ticket: Optional[str] = None):
        """Update trade on close"""
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE trades SET
                timestamp_close = ?, exit_price = ?, pnl_usd = ?,
                pnl_pct = ?, exit_reason = ?, mt5_ticket = ?
            WHERE trade_id = ?
        """, (datetime.utcnow().isoformat(), exit_price, pnl_usd,
              pnl_pct, exit_reason, mt5_ticket, trade_id))
        self.conn.commit()

    def log_signal(self, symbol: str, signal: str, price: float, 
                   ema_fast: float, ema_slow: float, atr: float):
        """Log strategy signal"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO signals (timestamp, symbol, signal, price, ema_fast, ema_slow, atr)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), symbol, signal, price, 
              ema_fast, ema_slow, atr))
        self.conn.commit()

    def log_equity(self, equity: float, open_pnl: float, daily_pnl: float, monthly_pnl: float):
        """Log equity snapshot"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO equity_curve (timestamp, equity, open_pnl, daily_pnl, monthly_pnl)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), equity, open_pnl, daily_pnl, monthly_pnl))
        self.conn.commit()

    def log_system(self, level: str, message: str):
        """Log system event"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO system_logs (timestamp, level, message)
            VALUES (?, ?, ?)
        """, (datetime.utcnow().isoformat(), level, message))
        self.conn.commit()

    def get_open_trades(self) -> List[Dict]:
        """Get all open trades"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM trades WHERE timestamp_close IS NULL
        """)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get recent closed trades"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM trades WHERE timestamp_close IS NOT NULL
            ORDER BY timestamp_close DESC LIMIT ?
        """, (limit,))
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_performance_stats(self) -> Dict:
        """Calculate performance statistics"""
        cursor = self.conn.cursor()

        # Total trades
        cursor.execute("SELECT COUNT(*) FROM trades WHERE timestamp_close IS NOT NULL")
        total = cursor.fetchone()[0]

        # Win rate
        cursor.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE timestamp_close IS NOT NULL AND pnl_usd > 0
        """)
        wins = cursor.fetchone()[0]

        # Averages
        cursor.execute("""
            SELECT AVG(pnl_usd), AVG(CASE WHEN pnl_usd > 0 THEN pnl_usd END),
                   AVG(CASE WHEN pnl_usd < 0 THEN pnl_usd END)
            FROM trades WHERE timestamp_close IS NOT NULL
        """)
        avg, avg_win, avg_loss = cursor.fetchone()

        # Total P&L
        cursor.execute("SELECT SUM(pnl_usd) FROM trades WHERE timestamp_close IS NOT NULL")
        total_pnl = cursor.fetchone()[0] or 0

        # Max drawdown (simplified)
        cursor.execute("""
            SELECT equity FROM equity_curve ORDER BY timestamp
        """)
        equities = [row[0] for row in cursor.fetchall()]
        max_dd = 0
        peak = 0
        for eq in equities:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return {
            "total_trades": total,
            "win_rate": (wins / total * 100) if total > 0 else 0,
            "avg_pnl": round(avg or 0, 2),
            "avg_win": round(avg_win or 0, 2),
            "avg_loss": round(avg_loss or 0, 2),
            "total_pnl": round(total_pnl, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "profit_factor": abs((avg_win * wins) / (avg_loss * (total - wins))) if avg_loss and (total - wins) > 0 else 0
        }

    def get_equity_curve(self, days: int = 30) -> List[Dict]:
        """Get equity curve data for charting"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT timestamp, equity, open_pnl FROM equity_curve
            WHERE timestamp > datetime('now', '-{} days')
            ORDER BY timestamp
        """.format(days))
        return [{"time": row[0], "equity": row[1], "open_pnl": row[2]} 
                for row in cursor.fetchall()]

# Singleton instance
db = TradeDatabase()
