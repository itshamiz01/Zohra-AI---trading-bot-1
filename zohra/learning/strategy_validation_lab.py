"""
╔══════════════════════════════════════════════════════════════════════╗
║   PHASE 4 — STRATEGY VALIDATION LAB                                  ║
║   Validates strategy performance matrix against historical data      ║
║   Measuring expectancy, win rates, drawdown, and profit factor.      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import sqlite3
import threading
import datetime as dt
import time
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np

logger = logging.getLogger("zohra.learning.validation_lab")


class StrategyValidationLab:
    """
    Backtests and validates registered strategies against historical HIE candles.
    Saves validation matrix to the hie_strategy_validation table.
    """

    def __init__(self, db_path: str = None):
        from zohra.hie.historical_data_engine import historical_data_engine
        # Save to HIE DB
        self.db_path = db_path or historical_data_engine.db_path_hie
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._init_table()

    def _init_table(self):
        """Create the validation matrix table if it doesn't exist."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS hie_strategy_validation (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp      TEXT NOT NULL,
                    strategy       TEXT NOT NULL,
                    symbol         TEXT NOT NULL,
                    timeframe      TEXT NOT NULL,
                    win_rate       REAL DEFAULT 0,
                    profit_factor  REAL DEFAULT 0,
                    avg_rr         REAL DEFAULT 0,
                    max_drawdown   REAL DEFAULT 0,
                    sharpe_ratio   REAL DEFAULT 0,
                    expectancy     REAL DEFAULT 0,
                    trades_count   INTEGER DEFAULT 0,
                    metrics_json   TEXT DEFAULT '{}',
                    UNIQUE(strategy, symbol, timeframe)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_val_strat ON hie_strategy_validation(strategy, symbol)")
            conn.commit()
            conn.close()
            logger.info("🔬 Strategy Validation Lab table initialized.")
        except Exception as e:
            logger.error(f"Failed to init Strategy Validation table: {e}")

    def start(self):
        """Start the background validation loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="HIE-ValidationLab")
        self._thread.start()
        logger.info("🔬 Strategy Validation Lab background loop started.")

    def stop(self):
        self._running = False

    def _run_loop(self):
        """Weekly validation sweep (runs on startup, then sleeps for 7 days)."""
        while self._running:
            try:
                logger.info("⚡ Starting scheduled strategy validation sweep...")
                self.run_full_validation_sweep()
                logger.info("✅ Strategy validation sweep completed.")
            except Exception as e:
                logger.error(f"Error in validation loop: {e}")
            
            # Sleep 7 days
            for _ in range(7 * 24):
                if not self._running:
                    break
                time.sleep(3600)

    def run_full_validation_sweep(self):
        """Run validation for all registered strategies on all HIE symbols."""
        from zohra.strategies.strategy_registry import strategy_registry
        from zohra.hie.historical_data_engine import HIE_SYMBOLS

        strategies = strategy_registry.get_all()
        timeframes = ["M15", "H1"] # standard backtest timeframes

        for meta in strategies:
            if not self._running:
                break
            for symbol in HIE_SYMBOLS:
                if not self._running:
                    break
                # Only backtest appropriate timeframes for the strategy
                applicable_tfs = [tf for tf in timeframes if tf in meta.applicable_timeframes]
                if not applicable_tfs:
                    applicable_tfs = [meta.applicable_timeframes[0]] # fallback to first timeframe

                for tf in applicable_tfs:
                    try:
                        metrics = self.backtest_strategy(meta.name, symbol, tf)
                        if metrics and metrics.get("trades_count", 0) > 0:
                            self._store_validation_results(meta.name, symbol, tf, metrics)
                    except Exception as e:
                        logger.error(f"Error backtesting {meta.name} on {symbol} {tf}: {e}")
                    time.sleep(0.05) # Rate-limit requests

    def backtest_strategy(self, strategy_name: str, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Runs a simulation of strategy signals over historical candles.
        Returns calculated metrics.
        """
        from zohra.strategies.strategy_registry import strategy_registry
        from zohra.hie.historical_data_engine import historical_data_engine
        
        meta = strategy_registry.get(strategy_name)
        if not meta or not meta.instance:
            return {}
            
        strategy_inst = meta.instance
        df = historical_data_engine.get_candles(symbol, timeframe, limit=1000)
        if df.empty or len(df) < 100:
            return {}
            
        trades = []
        i = 60 # wait for indicator warmups
        while i < len(df) - 1:
            df_slice = df.iloc[:i]
            sig = None
            try:
                sig = strategy_inst.generate_signal(df_slice, symbol)
            except Exception:
                pass
                
            if sig:
                direction = sig["direction"]
                entry = sig.get("entry_price") or sig.get("entry") or df.iloc[i]["close"]
                sl = sig.get("stop_loss") or sig.get("stop")
                tp = sig.get("take_profit") or sig.get("tp2") or sig.get("tp1")
                
                if sl and tp:
                    outcome = None
                    exit_price = entry
                    bars_held = 0
                    
                    # Track trade resolution in future candles
                    for j in range(i + 1, len(df)):
                        bars_held += 1
                        high = df.iloc[j]["high"]
                        low = df.iloc[j]["low"]
                        
                        if direction == "LONG":
                            if low <= sl:
                                outcome = -1.0 # Loss
                                exit_price = sl
                                break
                            elif high >= tp:
                                outcome = (tp - entry) / (entry - sl + 1e-9) # RRR
                                exit_price = tp
                                break
                        else:
                            if high >= sl:
                                outcome = -1.0 # Loss
                                exit_price = sl
                                break
                            elif low <= tp:
                                outcome = (entry - tp) / (sl - entry + 1e-9) # RRR
                                exit_price = tp
                                break
                                
                    if outcome is not None:
                        trades.append({
                            "direction": direction,
                            "entry": entry,
                            "exit": exit_price,
                            "pnl_r": outcome,
                            "bars": bars_held
                        })
                        # Jump forward to avoid overlaps
                        i += bars_held
                        continue
            i += 1
            
        if not trades:
            return {
                "win_rate": 0.0,
                "profit_factor": 1.0,
                "avg_rr": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "expectancy": 0.0,
                "trades_count": 0
            }
            
        # Compute stats
        wins = [t["pnl_r"] for t in trades if t["pnl_r"] > 0]
        losses = [t["pnl_r"] for t in trades if t["pnl_r"] < 0]
        
        trades_count = len(trades)
        win_rate = len(wins) / trades_count if trades_count > 0 else 0.0
        avg_rr = sum(wins) / len(wins) if wins else 0.0
        
        profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else (sum(wins) if wins else 1.0)
        expectancy = sum(t["pnl_r"] for t in trades) / trades_count
        
        equity_curve = [0.0]
        current_eq = 0.0
        for t in trades:
            current_eq += t["pnl_r"]
            equity_curve.append(current_eq)
            
        peak = -99999.0
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
                
        pnl_series = [t["pnl_r"] for t in trades]
        mean_pnl = np.mean(pnl_series)
        std_pnl = np.std(pnl_series)
        sharpe = float(mean_pnl / (std_pnl + 1e-9) * np.sqrt(252)) if std_pnl > 0 else 0.0
        
        return {
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 2),
            "avg_rr": round(avg_rr, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "expectancy": round(expectancy, 4),
            "trades_count": trades_count
        }

    def _store_results(self, strategy: str, symbol: str, timeframe: str, results: Dict) -> bool:
        """Internal helper to insert/replace validation records."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                INSERT OR REPLACE INTO hie_strategy_validation
                (timestamp, strategy, symbol, timeframe, win_rate, profit_factor, avg_rr, max_drawdown, sharpe_ratio, expectancy, trades_count, metrics_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                dt.datetime.utcnow().isoformat(),
                strategy, symbol, timeframe,
                results["win_rate"], results["profit_factor"], results["avg_rr"],
                results["max_drawdown"], results["sharpe_ratio"], results["expectancy"],
                results["trades_count"], json.dumps(results)
            ))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Failed to store validation results for {strategy}/{symbol}: {e}")
            return False

    def _store_validation_results(self, strategy: str, symbol: str, timeframe: str, results: Dict):
        self._store_results(strategy, symbol, timeframe, results)

    def get_validation_matrix(self, strategy: Optional[str] = None) -> List[Dict]:
        """Return the validation performance matrix."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if strategy:
                cursor.execute("SELECT * FROM hie_strategy_validation WHERE strategy=?", (strategy,))
            else:
                cursor.execute("SELECT * FROM hie_strategy_validation")
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to query validation matrix: {e}")
            return []


# Singleton
strategy_validation_lab = StrategyValidationLab()
