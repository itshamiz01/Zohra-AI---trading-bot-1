# zohra/learning/pattern_detector.py
import os
import json
import logging
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Tuple

logger = logging.getLogger("zohra.learning")

XGB_AVAILABLE = False
try:
    from xgboost import XGBClassifier
    XGB_AVAILABLE = True
except ImportError:
    pass

class LearningEngine:
    """
    Learning Engine for Zohra Command Center.
    Analyzes trade history from the database, detects winning and losing setup patterns,
    and generates actionable system recommendations.
    """
    def __init__(self, db_path: str = None):
        from zohra.config.settings import settings
        self.db_path = db_path or settings.DB_PATH
        self._init_learning_tables()

    def _init_learning_tables(self):
        """Ensure tables for recommendations and pattern discoveries exist in the DB."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            # Already checked by app.py, but make sure they are defined
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS learning_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    recommendation_text TEXT NOT NULL,
                    supporting_evidence TEXT NOT NULL,
                    applied INTEGER DEFAULT 0
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pattern_discoveries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_signature TEXT NOT NULL UNIQUE,
                    confluences TEXT NOT NULL, -- JSON list
                    occurrences INTEGER NOT NULL,
                    success_rate REAL NOT NULL,
                    avg_pnl REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS failure_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    failure_signature TEXT NOT NULL UNIQUE,
                    confluences TEXT NOT NULL, -- JSON list
                    occurrences INTEGER NOT NULL,
                    fail_rate REAL NOT NULL,
                    avg_loss REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing learning engine DB tables: {e}")

    def analyze_patterns(self) -> Dict[str, Any]:
        """
        Runs statistical / ML review over past trades to detect winning/losing setups,
        generates recommendations, and persists them to the database.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            df = pd.read_sql_query("SELECT * FROM trades WHERE pnl_usd IS NOT NULL", conn)
            conn.close()
            
            if len(df) < 10:
                logger.info("Insufficient trades logged in DB to run machine learning pattern detection (requires >= 10 trades).")
                return {
                    "status": "insufficient_data",
                    "trades_analyzed": len(df),
                    "suggestions": [
                        "Trading history is under 10 trades. Collect more trade samples to unlock automated ML optimization suggestion trees."
                    ]
                }
            
            # Label winning trades (pnl > 0)
            df['is_win'] = (df['pnl_usd'] > 0).astype(int)
            
            suggestions = []
            
            # 1. Statistical analysis by symbol
            symbol_stats = df.groupby('symbol').agg(
                trades=('id', 'count'),
                win_rate=('is_win', 'mean'),
                total_pnl=('pnl_usd', 'sum')
            ).reset_index()
            
            for _, row in symbol_stats.iterrows():
                symbol = row['symbol']
                cnt = row['trades']
                wr = row['win_rate']
                pnl = row['total_pnl']
                
                if cnt >= 5:
                    if wr < 0.40:
                        sug = f"Reduce risk sizing on {symbol} by 30%. Win rate is currently low at {wr:.1%} over {cnt} trades."
                        evidence = f"P&L of {symbol} is ${pnl:.2f} with {cnt} trades."
                        self._add_recommendation("RISK", sug, evidence)
                        suggestions.append(sug)
                    elif wr > 0.65:
                        sug = f"Increase prioritization & sizing weight for {symbol}. Strong win rate of {wr:.1%} over {cnt} trades."
                        evidence = f"P&L of {symbol} is +${pnl:.2f} over {cnt} trades."
                        self._add_recommendation("PRIORITY", sug, evidence)
                        suggestions.append(sug)

            # 2. Statistical analysis by session
            session_stats = df.groupby('session').agg(
                trades=('id', 'count'),
                win_rate=('is_win', 'mean'),
                total_pnl=('pnl_usd', 'sum')
            ).reset_index()
            
            for _, row in session_stats.iterrows():
                sess = row['session']
                cnt = row['trades']
                wr = row['win_rate']
                pnl = row['total_pnl']
                
                if cnt >= 5:
                    if wr < 0.40:
                        sug = f"Filter out lower priority trades during {sess.upper()} session. Win rate is {wr:.1%}."
                        evidence = f"Net P&L is ${pnl:.2f} for {sess} session entries."
                        self._add_recommendation("FILTER", sug, evidence)
                        suggestions.append(sug)

            # 3. Grade-level analysis for capital allocation and restrictions
            if 'quality_grade' in df.columns:
                grade_stats = df.groupby('quality_grade').agg(
                    trades=('id', 'count'),
                    win_rate=('is_win', 'mean'),
                    total_pnl=('pnl_usd', 'sum'),
                    avg_pnl=('pnl_usd', 'mean')
                ).reset_index()
                
                if not grade_stats.empty:
                    # Calculate profit factor and R-multiples per grade
                    for idx, row in grade_stats.iterrows():
                        g = row['quality_grade']
                        g_trades = df[df['quality_grade'] == g]
                        
                        # Profit factor per grade
                        gross_profit = g_trades[g_trades['pnl_usd'] > 0]['pnl_usd'].sum()
                        gross_loss = abs(g_trades[g_trades['pnl_usd'] < 0]['pnl_usd'].sum())
                        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
                        
                        # Average R-multiple per grade
                        if 'risk_usd' in g_trades.columns:
                            r_trades = g_trades[g_trades['risk_usd'] > 0].copy()
                            if not r_trades.empty:
                                r_trades['r_mult'] = r_trades['pnl_usd'] / r_trades['risk_usd']
                                avg_r = r_trades['r_mult'].mean()
                            else:
                                avg_r = 0.0
                        else:
                            avg_r = 0.0
                        
                        grade_stats.at[idx, 'profit_factor'] = pf
                        grade_stats.at[idx, 'avg_r_multiple'] = avg_r
                    
                    # Best performing grade by combined score (win_rate * 0.4 + profit_factor * 0.3 + avg_r * 0.3)
                    grade_stats['performance_score'] = (
                        grade_stats['win_rate'] * 0.4 + 
                        grade_stats['profit_factor'].clip(upper=5.0) / 5.0 * 0.3 + 
                        grade_stats['avg_r_multiple'].clip(lower=-2, upper=3).apply(lambda x: (x + 2) / 5.0) * 0.3
                    )
                    
                    best_idx = grade_stats['performance_score'].idxmax()
                    best_grade_row = grade_stats.loc[best_idx]
                    bg = best_grade_row['quality_grade']
                    b_wr = best_grade_row['win_rate']
                    b_trades = best_grade_row['trades']
                    b_pf = best_grade_row.get('profit_factor', 0)
                    b_avg_r = best_grade_row.get('avg_r_multiple', 0)
                    
                    if b_trades >= 3:
                        sug = (
                            f"Capital optimization: Setup grade {bg} is the best performer — "
                            f"Win Rate: {b_wr:.1%} | Profit Factor: {b_pf:.2f} | Avg R-Multiple: {b_avg_r:.2f}R. "
                            f"Recommend increasing risk allocation multiplier for {bg} setups."
                        )
                        evidence = f"Grade {bg} achieved ${best_grade_row['total_pnl']:.2f} P&L over {b_trades} trades with avg ${best_grade_row['avg_pnl']:.2f}/trade."
                        self._add_recommendation("CAPITAL", sug, evidence)
                        suggestions.append(sug)
                    
                    # Worst performing grade — restrict or disable
                    worst_idx = grade_stats['performance_score'].idxmin()
                    worst_grade_row = grade_stats.loc[worst_idx]
                    wg = worst_grade_row['quality_grade']
                    w_wr = worst_grade_row['win_rate']
                    w_trades = worst_grade_row['trades']
                    w_pf = worst_grade_row.get('profit_factor', 0)
                    w_avg_r = worst_grade_row.get('avg_r_multiple', 0)
                    
                    if w_trades >= 3 and (w_wr < 0.45 or w_pf < 1.0):
                        sug = (
                            f"Risk restriction: Setup grade {wg} is underperforming — "
                            f"Win Rate: {w_wr:.1%} | Profit Factor: {w_pf:.2f} | Avg R-Multiple: {w_avg_r:.2f}R. "
                            f"Recommend restricting or reducing position size for {wg} setups."
                        )
                        evidence = f"Grade {wg} has generated ${worst_grade_row['total_pnl']:.2f} P&L over {w_trades} trades."
                        self._add_recommendation("RESTRICTION", sug, evidence)
                        suggestions.append(sug)
                    
                    # Log full grade breakdown for transparency
                    for _, row in grade_stats.iterrows():
                        g = row['quality_grade']
                        logger.info(
                            f"📈 Learning Engine Grade Report: {g} | "
                            f"Trades: {int(row['trades'])} | Win Rate: {row['win_rate']:.1%} | "
                            f"PF: {row.get('profit_factor', 0):.2f} | "
                            f"Avg R: {row.get('avg_r_multiple', 0):.2f}R | "
                            f"P&L: ${row['total_pnl']:.2f}"
                        )

            # 4. Market conditions producing highest quality trades
            if 'market_regime' in df.columns and 'confidence_score' in df.columns:
                regime_quality = df.groupby('market_regime').agg(
                    trades=('id', 'count'),
                    avg_score=('confidence_score', 'mean'),
                    win_rate=('is_win', 'mean'),
                    total_pnl=('pnl_usd', 'sum')
                ).reset_index()
                
                if not regime_quality.empty:
                    best_reg_idx = regime_quality['avg_score'].idxmax()
                    best_regime_row = regime_quality.loc[best_reg_idx]
                    br = best_regime_row['market_regime']
                    b_score = best_regime_row['avg_score']
                    br_trades = best_regime_row['trades']
                    br_wr = best_regime_row['win_rate']
                    
                    if br_trades >= 3:
                        sug = (
                            f"Market condition match: {br} regime produces the highest quality setups "
                            f"(avg score {b_score:.1f}/100, win rate {br_wr:.1%}). "
                            f"Focus scans and increase exposure during {br} regimes."
                        )
                        evidence = f"{br} regime has avg confidence {b_score:.1f} and ${best_regime_row['total_pnl']:.2f} P&L over {br_trades} setups."
                        self._add_recommendation("CONDITION", sug, evidence)
                        suggestions.append(sug)

            # 5. Pattern Discovery Logging (Mock patterns or basic groupings)
            self._save_grouping_patterns(df)
            self._mine_cross_dimensional_confluences(df)

            return {
                "status": "success",
                "trades_analyzed": len(df),
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"Error in learning engine analysis: {e}", exc_info=True)
            return {"status": "error", "error": str(e), "suggestions": []}

    def _add_recommendation(self, category: str, text: str, evidence: str):
        """Adds a suggestion to database if it doesn't already exist."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM learning_recommendations 
                WHERE recommendation_text = ? AND applied = 0
            """, (text,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("""
                    INSERT INTO learning_recommendations (created_at, category, recommendation_text, supporting_evidence)
                    VALUES (?, ?, ?, ?)
                """, (datetime.utcnow().isoformat(), category, text, evidence))
                conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save recommendation to DB: {e}")

    def _save_grouping_patterns(self, df: pd.DataFrame):
        """Discovers common winning and failing setups using data aggregates and logs them."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            # Analyze combinations of Strategy + Session + Regime
            groups = df.groupby(['strategy_used', 'session', 'market_regime']).agg(
                occurrences=('id', 'count'),
                success_rate=('is_win', 'mean'),
                avg_pnl=('pnl_usd', 'mean')
            ).reset_index()
            
            for _, row in groups.iterrows():
                strat = row['strategy_used']
                sess = row['session']
                regime = row['market_regime']
                occ = int(row['occurrences'])
                rate = float(row['success_rate'])
                pnl = float(row['avg_pnl'])
                
                sig = f"{strat} + {sess.capitalize()} + {regime}"
                confl = [strat, sess, regime]
                
                if rate >= 0.60:
                    cursor.execute("""
                        INSERT OR REPLACE INTO pattern_discoveries (pattern_signature, confluences, occurrences, success_rate, avg_pnl)
                        VALUES (?, ?, ?, ?, ?)
                    """, (sig, json.dumps(confl), occ, rate * 100, pnl))
                else:
                    cursor.execute("""
                        INSERT OR REPLACE INTO failure_patterns (failure_signature, confluences, occurrences, fail_rate, avg_loss)
                        VALUES (?, ?, ?, ?, ?)
                    """, (sig, json.dumps(confl), occ, (1 - rate) * 100, pnl))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to save groupings: {e}")

    def _mine_cross_dimensional_confluences(self, df: pd.DataFrame):
        """
        Phase 9 — Cross-dimensional confluence mining:
        Discovers edge combinations across Strategy × Session × Regime × Symbol × ATR-level × Volume-level.
        """
        try:
            # Add helper categorization columns
            df = df.copy()
            if 'score_volatility' not in df.columns:
                df['score_volatility'] = 5
            if 'score_liquidity' not in df.columns:
                df['score_liquidity'] = 10
                
            df['atr_level'] = df['score_volatility'].apply(lambda x: 'High_ATR' if x >= 7 else 'Low_ATR')
            df['vol_level'] = df['score_liquidity'].apply(lambda x: 'High_Volume' if x >= 15 else 'Normal_Volume')
            
            group_cols = ['strategy_used', 'session', 'market_regime', 'symbol', 'atr_level', 'vol_level']
            
            # Filter rows where these columns are not null
            df_clean = df.dropna(subset=group_cols)
            
            if df_clean.empty:
                return
                
            groups = df_clean.groupby(group_cols).agg(
                occurrences=('id', 'count'),
                success_rate=('is_win', 'mean'),
                avg_pnl=('pnl_usd', 'mean')
            ).reset_index()
            
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()
            
            for _, row in groups.iterrows():
                strat = row['strategy_used']
                sess = row['session']
                regime = row['market_regime']
                sym = row['symbol']
                atr = row['atr_level']
                vol = row['vol_level']
                occ = int(row['occurrences'])
                rate = float(row['success_rate'])
                pnl = float(row['avg_pnl'])
                
                sig = f"{strat} x {sess.capitalize()} x {regime} x {sym} x {atr} x {vol}"
                confl = [strat, sess, regime, sym, atr, vol]
                
                if rate >= 0.60:
                    cursor.execute("""
                        INSERT OR REPLACE INTO pattern_discoveries (pattern_signature, confluences, occurrences, success_rate, avg_pnl)
                        VALUES (?, ?, ?, ?, ?)
                    """, (sig, json.dumps(confl), occ, rate * 100, pnl))
                else:
                    cursor.execute("""
                        INSERT OR REPLACE INTO failure_patterns (failure_signature, confluences, occurrences, fail_rate, avg_loss)
                        VALUES (?, ?, ?, ?, ?)
                    """, (sig, json.dumps(confl), occ, (1 - rate) * 100, pnl))
            
            conn.commit()
            conn.close()
            logger.info("📐 Cross-dimensional confluence mining complete.")
        except Exception as e:
            logger.error(f"Failed in cross-dimensional confluence mining: {e}")

# Singleton instance
learning_engine = LearningEngine()
