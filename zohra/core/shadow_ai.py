"""
╔══════════════════════════════════════════════════════════════════════╗
║                     ZOHRA — SHADOW AI ENGINE                         ║
║         Virtual Trade Simulation & Comparative Learning              ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import sqlite3
from datetime import datetime
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH
from zohra.brokers.manager import broker_manager as mt5_broker

logger = logging.getLogger("zohra.shadow_ai")

class ShadowAIEngine:
    """
    Simulates and tracks virtual alternative trading decisions in parallel with live trades.
    Allows the Zohra Learning Engine to compare outcomes and recommend strategy optimizations.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initializes the shadow_trades table if it does not exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS shadow_trades (
                        id TEXT PRIMARY KEY,
                        parent_trade_id TEXT,
                        shadow_type TEXT, -- 'OPPOSITE', 'ALT_SL_TP', 'FIXED_2RR'
                        symbol TEXT,
                        direction TEXT,
                        entry_price REAL,
                        stop_loss REAL,
                        take_profit REAL,
                        volume REAL,
                        status TEXT, -- 'ACTIVE', 'CLOSED'
                        pnl_usd REAL,
                        result TEXT, -- 'WIN', 'LOSS', 'CANCELLED'
                        opened_at TEXT,
                        closed_at TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize shadow_trades table: {e}")

    def spawn_shadow_trades(self, parent_trade_id: str, symbol: str, direction: str, 
                            entry_price: float, stop_loss: float, take_profit: float, volume: float):
        """Spawns 3 shadow trades for a given parent trade."""
        try:
            risk = abs(entry_price - stop_loss)
            if risk == 0:
                return

            shadows = []
            now_str = datetime.utcnow().isoformat()

            # 1. OPPOSITE Direction Trade
            opp_dir = "SHORT" if direction == "LONG" else "LONG"
            opp_sl = entry_price + (entry_price - stop_loss) # Inverse SL
            opp_tp = entry_price - (entry_price - stop_loss) * 2.0 # Target 2R in opposite direction
            shadows.append({
                "id": f"shadow_opp_{parent_trade_id}",
                "parent_trade_id": parent_trade_id,
                "shadow_type": "OPPOSITE",
                "direction": opp_dir,
                "stop_loss": opp_sl,
                "take_profit": opp_tp
            })

            # 2. ALTERNATIVE SL/TP (Wider SL, Higher Target)
            alt_sl = entry_price - (entry_price - stop_loss) * 1.5 if direction == "LONG" else entry_price + (stop_loss - entry_price) * 1.5
            alt_tp = entry_price + (take_profit - entry_price) * 1.5 if direction == "LONG" else entry_price - (entry_price - take_profit) * 1.5
            shadows.append({
                "id": f"shadow_alt_{parent_trade_id}",
                "parent_trade_id": parent_trade_id,
                "shadow_type": "ALT_SL_TP",
                "direction": direction,
                "stop_loss": alt_sl,
                "take_profit": alt_tp
            })

            # 3. FIXED 1:2 RISK-TO-REWARD (No trailing stop, pure take profit)
            fixed_tp = entry_price + (risk * 2.0) if direction == "LONG" else entry_price - (risk * 2.0)
            shadows.append({
                "id": f"shadow_fixed_{parent_trade_id}",
                "parent_trade_id": parent_trade_id,
                "shadow_type": "FIXED_2RR",
                "direction": direction,
                "stop_loss": stop_loss,
                "take_profit": fixed_tp
            })

            # Insert into database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for sh in shadows:
                    cursor.execute("""
                        INSERT INTO shadow_trades 
                        (id, parent_trade_id, shadow_type, symbol, direction, entry_price, stop_loss, take_profit, volume, status, pnl_usd, result, opened_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 0.0, 'PENDING', ?)
                    """, (
                        sh["id"], sh["parent_trade_id"], sh["shadow_type"], symbol, sh["direction"],
                        entry_price, sh["stop_loss"], sh["take_profit"], volume, now_str
                    ))
                conn.commit()
            logger.info(f"👥 Spawned 3 shadow trades for parent trade #{parent_trade_id}")

        except Exception as e:
            logger.error(f"Failed to spawn shadow trades: {e}")

    def update_shadow_trades(self):
        """Updates all active shadow trades against current market prices."""
        try:
            active_shadows = []
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM shadow_trades WHERE status = 'ACTIVE'")
                active_shadows = [dict(row) for row in cursor.fetchall()]

            if not active_shadows:
                return

            # Get unique symbols to fetch prices in one go
            symbols = list(set(sh["symbol"] for sh in active_shadows))
            prices = {}
            for sym in symbols:
                tick = mt5_broker.get_tick(sym)
                if tick:
                    prices[sym] = {
                        "bid": tick.get("bid"),
                        "ask": tick.get("ask")
                    }

            closed_count = 0
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for sh in active_shadows:
                    sym = sh["symbol"]
                    if sym not in prices:
                        continue

                    direction = sh["direction"]
                    entry = sh["entry_price"]
                    sl = sh["stop_loss"]
                    tp = sh["take_profit"]
                    vol = sh["volume"]
                    
                    # Determine current price based on direction
                    current_price = prices[sym]["bid"] if direction == "LONG" else prices[sym]["ask"]
                    if not current_price:
                        continue

                    # Calculate potential PnL in points
                    # Assuming standard EURUSD/Gold pip values for simple estimation
                    # (For exact USD calculation, we can scale by volume/contract size)
                    point_multiplier = 100000.0 if "JPY" not in sym and sym != "XAUUSD" else 100.0
                    pnl_points = (current_price - entry) if direction == "LONG" else (entry - current_price)
                    estimated_pnl = pnl_points * point_multiplier * vol * 10.0 # Approx USD PnL

                    hit_sl = False
                    hit_tp = False

                    if direction == "LONG":
                        if current_price <= sl:
                            hit_sl = True
                        elif current_price >= tp:
                            hit_tp = True
                    else:
                        if current_price >= sl:
                            hit_sl = True
                        elif current_price <= tp:
                            hit_tp = True

                    if hit_sl or hit_tp:
                        status = "CLOSED"
                        result = "LOSS" if hit_sl else "WIN"
                        now_str = datetime.utcnow().isoformat()
                        
                        cursor.execute("""
                            UPDATE shadow_trades 
                            SET status = 'CLOSED', pnl_usd = ?, result = ?, closed_at = ?
                            WHERE id = ?
                        """, (estimated_pnl, result, now_str, sh["id"]))
                        closed_count += 1
                        logger.info(f"👥 Shadow Trade {sh['id']} ({sh['shadow_type']}) closed as {result} with PnL: ${estimated_pnl:+.2f}")

                conn.commit()

        except Exception as e:
            logger.error(f"Failed to update shadow_trades: {e}")

# Singleton
shadow_ai_engine = ShadowAIEngine()
