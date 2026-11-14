import sqlite3
import datetime
import json
import os
import math
import logging
import random
import time
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
from zohra.utils.mt5_connection import mt5
from typing import Dict, List, Any, Optional

# OpenRouter & Groq AI Providers

logger = logging.getLogger("zohra.analytics.advanced")

# Path to database
DB_PATH = os.getenv("DB_PATH", "logs/zohra_trades.db")

class AdvancedAnalyticsManager:
    def __init__(self):
        self.db_path = DB_PATH

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_analysis_query(self, sql: str) -> List[Dict[str, Any]]:
        """Treat model-generated SQL as untrusted, bounded, read-only input."""
        if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
            raise ValueError("Expected a single bounded analysis query")
        tables = {"trades", "rejected_trades", "equity_curve", "learning_recommendations",
                  "pattern_discoveries", "failure_patterns"}
        functions = {"count", "sum", "avg", "min", "max", "total", "round", "abs", "coalesce",
                     "ifnull", "nullif", "lower", "upper", "length", "substr", "substring",
                     "date", "datetime", "strftime", "julianday", "unixepoch", "like"}

        def authorize(action, arg1, arg2, database, trigger):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_READ and database == "main" and arg1 in tables:
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in functions:
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        conn = self._get_connection()
        try:
            conn.execute("PRAGMA query_only = ON")
            conn.set_authorizer(authorize)
            deadline = time.monotonic() + 2
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            return [dict(row) for row in conn.execute(sql).fetchmany(1000)]
        finally:
            conn.close()

    # ════════════════════════════════════════════════
    #  PHASE 3: PORTFOLIO RISK & EXPOSURE
    # ════════════════════════════════════════════════
    def calculate_portfolio_exposures(self) -> Dict[str, Any]:
        """Calculates exposure for USD, JPY, EUR, GBP, CAD, AUD, NZD, CHF, Gold, Silver."""
        exposures = {
            "USD": 0.0, "JPY": 0.0, "EUR": 0.0, "GBP": 0.0,
            "CAD": 0.0, "AUD": 0.0, "NZD": 0.0, "CHF": 0.0,
            "XAU": 0.0, "XAG": 0.0
        }
        
        if not mt5:
            return {"exposures": exposures, "error": "MT5 not initialized"}

        positions = mt5.positions_get()
        if not positions:
            return {"exposures": exposures, "total_exposure_usd": 0.0}

        total_exposure_usd = 0.0
        for pos in positions:
            symbol = pos.symbol
            lots = pos.volume
            direction = pos.type # 0 = BUY, 1 = SELL
            price = pos.price_open
            
            # Estimate USD size
            contract_size = 100000.0
            if "XAU" in symbol:
                contract_size = 100.0
            elif "XAG" in symbol:
                contract_size = 5000.0
            
            lot_usd_value = contract_size * price
            # Decompose currencies
            # Simple direct calculation based on pairs
            base = symbol[:3]
            quote = symbol[3:6]
            
            if symbol == "XAUUSD":
                base, quote = "XAU", "USD"
            elif symbol == "XAGUSD":
                base, quote = "XAG", "USD"

            mult = 1.0 if direction == 0 else -1.0
            trade_value_usd = lots * lot_usd_value * mult
            total_exposure_usd += abs(trade_value_usd)

            # Base currency exposure
            if base in exposures:
                exposures[base] += trade_value_usd
            # Quote currency exposure (short/long opposite)
            if quote in exposures:
                exposures[quote] -= trade_value_usd

        # Log to db
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_exposure (timestamp, sector_exposures, currency_stack, margin_used, free_margin, margin_level)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.datetime.utcnow().isoformat(),
                json.dumps({"Forex": len(positions)}),
                json.dumps(exposures),
                0.0, 0.0, 0.0
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging exposure snapshot: {e}")

        return {
            "exposures": exposures,
            "total_exposure_usd": round(total_exposure_usd, 2)
        }

    # ════════════════════════════════════════════════
    #  PHASE 4: CORRELATION ENGINE
    # ════════════════════════════════════════════════
    def get_correlations(self) -> Dict[str, Any]:
        """Calculates Pearson correlation metrics for the main trading symbols."""
        symbols = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "XAUUSD"]
        
        if not mt5 or not mt5.terminal_info():
            return {"status": "unavailable", "matrix": {}, "alerts": ["Broker history unavailable"]}

        # Copy closing prices
        data = {}
        for sym in symbols:
            rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 72) # 3 days of hourly data
            if rates is not None and len(rates) > 0:
                data[sym] = [r['close'] for r in rates]
        
        if len(data) < 2:
            return {"status": "unavailable", "matrix": {}, "alerts": ["Insufficient broker history"]}
        symbols = list(data)
        matrix = {}
        for s1 in symbols:
            matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                elif s1 in data and s2 in data:
                    # Pearson correlation calculation
                    prices1 = data[s1]
                    prices2 = data[s2]
                    n = min(len(prices1), len(prices2))
                    if n > 2:
                        p1 = prices1[-n:]
                        p2 = prices2[-n:]
                        mean1 = sum(p1) / n
                        mean2 = sum(p2) / n
                        cov = sum((p1[i] - mean1) * (p2[i] - mean2) for i in range(n))
                        var1 = sum((p1[i] - mean1) ** 2 for i in range(n))
                        var2 = sum((p2[i] - mean2) ** 2 for i in range(n))
                        denom = math.sqrt(var1 * var2)
                        matrix[s1][s2] = round(cov / denom, 2) if denom > 0 else 0.0
                else:
                    matrix[s1][s2] = 0.0

        # Save to DB cache
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM correlation_matrix_cache")
            cursor.execute("""
                INSERT INTO correlation_matrix_cache (matrix_json, updated_at)
                VALUES (?, ?)
            """, (json.dumps(matrix), datetime.datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error caching correlation: {e}")

        # Check for alerts
        alerts = []
        for s1 in symbols:
            for s2 in symbols:
                if s1 < s2 and abs(matrix[s1].get(s2, 0.0)) > 0.8:
                    alerts.append(f"High Correlation Warning: {s1} vs {s2} ({matrix[s1][s2]})")

        return {"matrix": matrix, "alerts": alerts}

    # ════════════════════════════════════════════════
    #  PHASE 5: RISK CONCENTRATION ENGINE
    # ════════════════════════════════════════════════
    def get_risk_concentration(self) -> Dict[str, Any]:
        """Tracks risk concentrations and emits alerts."""
        exposure_data = self.calculate_portfolio_exposures()
        exposures = exposure_data.get("exposures", {})
        total_exp = exposure_data.get("total_exposure_usd", 0.0)

        alerts = []
        recommendations = []
        if total_exp > 0:
            for cur, val in exposures.items():
                pct = (abs(val) / total_exp) * 100
                if pct > 50:
                    alerts.append(f"Risk Concentration Alert: {pct:.1f}% of absolute exposure is tied to {cur} basket.")
                    recommendations.append(f"Suggest pausing or reducing position size for new {cur} trades.")
        
        return {
            "concentrations": {k: abs(v) for k, v in exposures.items()},
            "alerts": alerts,
            "recommendations": recommendations
        }

    # ════════════════════════════════════════════════
    #  PHASE 6: MARGIN HEALTH MONITOR
    # ════════════════════════════════════════════════
    def get_margin_health(self) -> Dict[str, Any]:
        """Monitors leverage, margin levels, and liquidation risks."""
        if not mt5:
            return {"error": "MT5 not connected"}
        
        account = mt5.account_info()
        if not account:
            return {"error": "Failed to fetch account info"}

        margin_used = account.margin
        free_margin = account.margin_free
        margin_level = account.margin_level
        leverage = account.leverage
        equity = account.equity
        balance = account.balance
        
        # Risk estimation
        liq_risk = "LOW"
        if margin_level > 0 and margin_level < 150.0:
            liq_risk = "CRITICAL"
        elif margin_level > 0 and margin_level < 300.0:
            liq_risk = "HIGH"

        warnings = []
        if liq_risk in ["CRITICAL", "HIGH"]:
            warnings.append(f"MARGIN STRESS WARNING: Account margin level is dangerously low ({margin_level:.1f}%).")

        # Save risk events if critical
        if liq_risk == "CRITICAL":
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO risk_events (timestamp, event_type, description, action_taken)
                    VALUES (?, ?, ?, ?)
                """, (datetime.datetime.utcnow().isoformat(), "MARGIN_STRESS", f"Margin level dropped to {margin_level:.2f}%", "MONITORING"))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Error logging risk event: {e}")

        return {
            "margin_used": margin_used,
            "free_margin": free_margin,
            "margin_level": margin_level,
            "leverage": leverage,
            "equity": equity,
            "balance": balance,
            "liquidation_risk": liq_risk,
            "warnings": warnings
        }

    # ════════════════════════════════════════════════
    #  PHASE 7 - 10: COMPARATIVE PERFORMANCE ANALYTICS
    # ════════════════════════════════════════════════
    def get_strategy_performance(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strategy_used, COUNT(*) as trades,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN pnl_usd <= 0 THEN 1 ELSE 0 END) as losses,
            SUM(pnl_usd) as pnl,
            AVG(duration_minutes) as hold_time,
            AVG(risk_reward_ratio) as rr
            FROM trades
            WHERE timestamp_close IS NOT NULL
            GROUP BY strategy_used
        """)
        rows = cursor.fetchall()
        
        strats = {}
        for r in rows:
            name = r['strategy_used'] or "SMC"
            wins = r['wins']
            losses = r['losses']
            total = r['trades']
            wr = (wins / total * 100) if total > 0 else 0
            
            strats[name] = {
                "trades": total,
                "wins": wins,
                "losses": losses,
                "pnl": round(r['pnl'] or 0.0, 2),
                "win_rate": round(wr, 1),
                "avg_hold_time": round(r['hold_time'] or 0.0, 1),
                "avg_rr": round(r['rr'] or 0.0, 2)
            }
        conn.close()
        return strats

    def get_grade_performance(self) -> Dict[str, Any]:
        """Compute performance breakdown by Trade Quality Grade (A+, A, B, C)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT quality_grade, pnl_usd, risk_usd, risk_reward_ratio, metadata
            FROM trades
            WHERE timestamp_close IS NOT NULL
        """)
        trades_rows = cursor.fetchall()
        conn.close()
        
        grades = ["A+", "A", "B", "C"]
        grade_data = {g: [] for g in grades}
        for r in trades_rows:
            g = r['quality_grade']
            if g in grade_data:
                grade_data[g].append(r)
                
        results = {}
        for g in grades:
            t_list = grade_data[g]
            total = len(t_list)
            if total == 0:
                results[g] = {
                    "trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "pnl": 0.0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "avg_drawdown": 0.0,
                    "avg_r_multiple": 0.0,
                    "expected_value": 0.0
                }
                continue
                
            wins = sum(1 for t in t_list if (t['pnl_usd'] or 0.0) > 0)
            losses = sum(1 for t in t_list if (t['pnl_usd'] or 0.0) <= 0)
            pnl = sum((t['pnl_usd'] or 0.0) for t in t_list)
            wr = (wins / total * 100) if total > 0 else 0
            
            gross_profit = sum((t['pnl_usd'] or 0) for t in t_list if (t['pnl_usd'] or 0) > 0)
            gross_loss = abs(sum((t['pnl_usd'] or 0) for t in t_list if (t['pnl_usd'] or 0) < 0))
            
            if gross_loss > 0:
                pf = gross_profit / gross_loss
            else:
                pf = 999.0 if gross_profit > 0 else 0.0
            
            # Drawdowns from metadata
            drawdowns = []
            for t in t_list:
                dd = 0.0
                meta_str = t['metadata']
                if meta_str:
                    try:
                        import json
                        meta = json.loads(meta_str)
                        dd = float(meta.get('drawdown_pct', 0.0))
                    except Exception:
                        pass
                drawdowns.append(dd)
            avg_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0.0
            
            # R-Multiple calculation: pnl / risk_usd
            r_multiples = []
            for t in t_list:
                p_val = t['pnl_usd']
                r_val = t['risk_usd']
                if p_val is not None and r_val and r_val > 0:
                    r_multiples.append(p_val / r_val)
            avg_r_mult = sum(r_multiples) / len(r_multiples) if r_multiples else 0.0
            
            # Expected value
            expected_value = pnl / total if total > 0 else 0.0
            
            results[g] = {
                "trades": total,
                "wins": wins,
                "losses": losses,
                "pnl": round(pnl, 2),
                "win_rate": round(wr, 1),
                "profit_factor": round(pf, 2),
                "avg_drawdown": round(avg_dd, 2),
                "avg_r_multiple": round(avg_r_mult, 2),
                "expected_value": round(expected_value, 2)
            }
            
        return results

    def get_market_condition_performance(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT market_regime, COUNT(*) as trades,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
            SUM(pnl_usd) as pnl
            FROM trades
            WHERE timestamp_close IS NOT NULL
            GROUP BY market_regime
        """)
        rows = cursor.fetchall()
        regimes = {}
        for r in rows:
            name = r['market_regime'] or "Trending"
            total = r['trades']
            wins = r['wins']
            regimes[name] = {
                "trades": total,
                "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                "pnl": round(r['pnl'] or 0.0, 2)
            }
        conn.close()
        return regimes

    def get_session_performance(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session, COUNT(*) as trades,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
            SUM(pnl_usd) as pnl
            FROM trades
            WHERE timestamp_close IS NOT NULL
            GROUP BY session
        """)
        rows = cursor.fetchall()
        sessions = {}
        for r in rows:
            name = r['session'] or "London"
            total = r['trades']
            wins = r['wins']
            sessions[name] = {
                "trades": total,
                "win_rate": round((wins / total * 100) if total > 0 else 0, 1),
                "pnl": round(r['pnl'] or 0.0, 2)
            }
        conn.close()
        return sessions

    def get_timeframe_performance(self) -> Dict[str, Any]:
        # Since we trade scalp_m5, let's categorize timeframes based on strategy name
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT strategy_used, COUNT(*) as trades,
            SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
            SUM(pnl_usd) as pnl
            FROM trades
            WHERE timestamp_close IS NOT NULL
            GROUP BY strategy_used
        """)
        rows = cursor.fetchall()
        timeframes = {"M1": {"trades": 0, "win_rate": 0, "pnl": 0.0},
                      "M5": {"trades": 0, "win_rate": 0, "pnl": 0.0},
                      "M15": {"trades": 0, "win_rate": 0, "pnl": 0.0}}
                      
        wins_by_timeframe = {key: 0 for key in timeframes}
        for r in rows:
            strat = r['strategy_used'] or ""
            tf = "M5"
            if "m15" in strat.lower():
                tf = "M15"
            elif "m1" in strat.lower():
                tf = "M1"
                
            timeframes[tf]["trades"] += r["trades"]
            wins_by_timeframe[tf] += r["wins"] or 0
            timeframes[tf]["pnl"] += r["pnl"] or 0.0
            
        for tf, data in timeframes.items():
            if data["trades"] > 0:
                data["win_rate"] = round(wins_by_timeframe[tf] / data["trades"] * 100, 1)
            data["pnl"] = round(data["pnl"], 2)
            
        conn.close()
        return timeframes

    # ════════════════════════════════════════════════
    #  PHASE 11: MISSED OPPORTUNITY ENGINE
    # ════════════════════════════════════════════════
    def get_missed_opportunities(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM rejected_trades")
        rejected_cnt = cursor.fetchone()['cnt']
        
        # Calculate missed profit / successful rejections
        # Let's read from opportunity_history table
        cursor.execute("""
            SELECT status, COUNT(*) as count, SUM(CASE WHEN decision_reason LIKE '%hit TP%' THEN 1 ELSE 0 END) as tp_hits
            FROM opportunity_history
            GROUP BY status
        """)
        rows = cursor.fetchall()
        
        missed_profit = 0.0
        bullets_avoided = 0.0
        
        for r in rows:
            status = r['status']
            if status == "MISSED_PROFIT":
                missed_profit = r['count'] * 12.50 # estimate $12.50 per missed trade
            elif status == "BULLET_AVOIDED":
                bullets_avoided = r['count'] * 8.40 # estimate $8.40 saved per avoid
                
        conn.close()
        return {
            "total_rejected": rejected_cnt,
            "missed_profit_usd": None,
            "bullets_avoided_saved_usd": None,
            "opportunities_score": None,
            "outcomes": [dict(row) for row in rows],
            "valuation_status": "Counterfactual price outcomes have not been measured"
        }

    # ════════════════════════════════════════════════
    #  PHASE 12: FALSE SIGNAL ANALYSIS
    # ════════════════════════════════════════════════
    def get_false_signals(self) -> Dict[str, Any]:
        """Ranks indicators by false signal frequency."""
        # Query score columns
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(score_structure) as struct, AVG(score_liquidity) as liq,
            AVG(score_smc) as smc, AVG(score_trend) as trend, AVG(score_momentum) as mom,
            AVG(score_volatility) as vol
            FROM trades
            WHERE timestamp_close IS NOT NULL AND pnl_usd > 0
        """)
        win_scores = cursor.fetchone()
        
        cursor.execute("""
            SELECT AVG(score_structure) as struct, AVG(score_liquidity) as liq,
            AVG(score_smc) as smc, AVG(score_trend) as trend, AVG(score_momentum) as mom,
            AVG(score_volatility) as vol
            FROM trades
            WHERE timestamp_close IS NOT NULL AND pnl_usd < 0
        """)
        loss_scores = cursor.fetchone()
        
        rankings = []
        indicators = [
            ("Structure Reliability", win_scores['struct'], loss_scores['struct']),
            ("Liquidity Sweep Reliability", win_scores['liq'], loss_scores['liq']),
            ("SMC Analysis Reliability", win_scores['smc'], loss_scores['smc']),
            ("Trend Factor Reliability", win_scores['trend'], loss_scores['trend']),
            ("Momentum Scan Reliability", win_scores['mom'], loss_scores['mom']),
            ("Volatility Ratio Reliability", win_scores['vol'], loss_scores['vol'])
        ]
        
        for name, win_val, loss_val in indicators:
            if win_val is None or loss_val is None:
                continue
            diff = win_val - loss_val
            reliability = 50.0 + (diff * 2)
            rankings.append({
                "indicator": name,
                "reliability_score": round(max(10.0, min(99.0, reliability)), 1)
            })
            
        rankings = sorted(rankings, key=lambda x: x["reliability_score"], reverse=True)
        conn.close()
        return {"rankings": rankings}

    # ════════════════════════════════════════════════
    #  PHASE 13 & 14: LATENCY, SPREADS & BROKER PERFORMANCE
    # ════════════════════════════════════════════════
    def get_broker_performance(self) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AVG(execution_delay_ms) as delay, AVG(latency_ms) as latency,
            AVG(spread_at_entry) as spread, AVG(slippage_points) as slippage
            FROM execution_metrics
        """)
        row = cursor.fetchone()
        
        def measured(key, digits):
            return round(row[key], digits) if row[key] is not None else None
        
        conn.close()
        return {
            "execution_delay_ms": measured("delay", 1),
            "broker_latency_ms": measured("latency", 1),
            "average_spread_pips": measured("spread", 2),
            "average_slippage_points": measured("slippage", 2),
            "connection_stability_pct": None,
            "broker_fill_quality": None
        }

    # ════════════════════════════════════════════════
    #  PHASE 15 - 18: AI LEARNING & PATTERN DISCOVERIES
    # ════════════════════════════════════════════════
    def get_ai_learning_insights(self) -> Dict[str, Any]:
        """Identifies winning patterns, failure patterns, and setting changes."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Recommendations
        cursor.execute("SELECT recommendation_text, supporting_evidence FROM learning_recommendations WHERE is_active=1")
        rec_rows = cursor.fetchall()
        recs = [r['recommendation_text'] for r in rec_rows]

        # Discoveries
        cursor.execute("SELECT pattern_signature, success_rate FROM pattern_discoveries")
        pat_rows = cursor.fetchall()
        pats = [{"pattern": r['pattern_signature'], "win_rate": r['success_rate']} for r in pat_rows]

        # Failures
        cursor.execute("SELECT failure_signature, fail_rate FROM failure_patterns")
        fail_rows = cursor.fetchall()
        fails = [{"pattern": r['failure_signature'], "fail_rate": r['fail_rate']} for r in fail_rows]

        conn.close()
        return {
            "recommendations": recs,
            "profitable_patterns": pats,
            "failure_patterns": fails,
            "calibration_score": None
        }

    # ════════════════════════════════════════════════
    #  PHASE 22 & 23: SYSTEM HEALTH & MODULE HEALTH
    # ════════════════════════════════════════════════
    def get_system_health(self) -> Dict[str, Any]:
        if PSUTIL_AVAILABLE:
            try:
                cpu = psutil.cpu_percent()
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
            except Exception:
                cpu, ram, disk = None, None, None
        else:
            cpu, ram, disk = None, None, None
        
        # Modules running check
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT module_name, status, latency_ms FROM module_health")
        rows = cursor.fetchall()
        modules = {}
        for r in rows:
            modules[r['module_name']] = {
                "status": r['status'],
                "latency_ms": r['latency_ms']
            }
            
        # Default fallback states if empty
        default_modules = [
            "SMC Module", "Risk Engine", "Execution Engine",
            "News Engine", "Memory Engine", "Learning Engine"
        ]
        for dm in default_modules:
            if dm not in modules:
                modules[dm] = {"status": "UNKNOWN", "latency_ms": None}
                
        conn.close()
        return {
            "cpu_usage_pct": cpu,
            "ram_usage_pct": ram,
            "disk_usage_pct": disk,
            "database_connected": True,
            "mt5_connected": bool(mt5 and mt5.terminal_info()),
            "modules": modules
        }

    # ════════════════════════════════════════════════
    #  PHASE 25: NATURAL LANGUAGE QUERY ENGINE
    # ════════════════════════════════════════════════
    def route_natural_language_query(self, query: str) -> str:
        """Parses English-language questions and routes them to SQL database lookups."""
        q = query.lower().strip()
        
        # Determine if we should use OpenRouter or Groq
        provider = os.getenv("CHAT_PROVIDER", "openrouter").lower()
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        groq_key = os.getenv("GROQ_API_KEY")
        
        use_openrouter = (provider == "openrouter" and bool(openrouter_key)) or (bool(openrouter_key) and not (provider == "groq" and groq_key))
        use_groq = (provider == "groq" and bool(groq_key)) or (bool(groq_key) and not use_openrouter)
        
        if use_openrouter:
            import requests
            try:
                url = "https://openrouter.ai/api/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/ZohraQuant/trading_bot",
                    "X-Title": "Zohra AI Command Center"
                }
                
                sql_prompt = f"""
                You are Zohra AI's Database Analyst. Convert the following English user query into a single valid SQLite query.
                Target tables:
                - trades (columns: id, trade_id, mt5_ticket, timestamp_open, timestamp_close, symbol, direction, entry_price, exit_price, stop_loss, take_profit, position_size_lots, risk_usd, pnl_usd, pnl_pct, risk_reward_ratio, confidence_score, quality_grade, session, market_regime, strategy_used, news_status, reason_for_entry, reason_for_exit, exit_reason_code)
                - rejected_trades (columns: id, timestamp, symbol, direction, confidence_score, failed_conditions, reason_for_rejection, session, market_regime, strategy)
                - equity_curve (columns: id, timestamp, equity, open_pnl, daily_pnl, weekly_pnl, monthly_pnl, drawdown_pct)
                - learning_recommendations (columns: id, created_at, category, recommendation_text, supporting_evidence, applied)
                - pattern_discoveries (columns: id, pattern_signature, confluences, occurrences, success_rate, avg_pnl)
                - failure_patterns (columns: id, failure_signature, confluences, occurrences, fail_rate, avg_loss)
                
                User request: "{query}"
                Output only the SQLite SQL statement. No markdown boxes, no other text.
                """
                
                payload = {
                    "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": "You are Zohra AI's Database Analyst. Output ONLY standard SQLite statement. No explanation, no backticks, no markdown formatting."},
                        {"role": "user", "content": sql_prompt}
                    ],
                    "temperature": 0.1
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                sql_resp = response.json()["choices"][0]["message"]["content"].strip()
                sql = sql_resp.replace("```sql", "").replace("```", "").replace("`", "").strip()
                
                data_summary = self._read_analysis_query(sql)
                
                # Synthesize explanation
                summary_prompt = f"""
                You are Zohra AI. Summarize the query results in a clear, professional, direct plain English explanation.
                User request: "{query}"
                SQL executed: "{sql}"
                Query results (JSON format):
                ```json
                {json.dumps(data_summary[:10], indent=2)}
                ```
                Provide a short quantitative summary. Never make up numbers not present in the results. If no records are found, say 'I do not have enough data.'
                """
                
                payload_summary = {
                    "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                    "messages": [
                        {"role": "system", "content": "You are Zohra AI. Summarize the query results in a clear, professional, direct plain English explanation."},
                        {"role": "user", "content": summary_prompt}
                    ],
                    "temperature": 0.3
                }
                
                response_sum = requests.post(url, headers=headers, json=payload_summary, timeout=10)
                response_sum.raise_for_status()
                summary_resp = response_sum.json()["choices"][0]["message"]["content"].strip()
                return summary_resp
            except Exception as e:
                logger.warning(f"OpenRouter SQL routing failed: {e}. Falling back to pattern-based router.")
        
        elif use_groq:
            import requests
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                }
                
                sql_prompt = f"""
                You are Zohra AI's Database Analyst. Convert the following English user query into a single valid SQLite query.
                Target tables:
                - trades (columns: id, trade_id, mt5_ticket, timestamp_open, timestamp_close, symbol, direction, entry_price, exit_price, stop_loss, take_profit, position_size_lots, risk_usd, pnl_usd, pnl_pct, risk_reward_ratio, confidence_score, quality_grade, session, market_regime, strategy_used, news_status, reason_for_entry, reason_for_exit, exit_reason_code)
                - rejected_trades (columns: id, timestamp, symbol, direction, confidence_score, failed_conditions, reason_for_rejection, session, market_regime, strategy)
                - equity_curve (columns: id, timestamp, equity, open_pnl, daily_pnl, weekly_pnl, monthly_pnl, drawdown_pct)
                - learning_recommendations (columns: id, created_at, category, recommendation_text, supporting_evidence, applied)
                - pattern_discoveries (columns: id, pattern_signature, confluences, occurrences, success_rate, avg_pnl)
                - failure_patterns (columns: id, failure_signature, confluences, occurrences, fail_rate, avg_loss)
                
                User request: "{query}"
                Output only the SQLite SQL statement. No markdown boxes, no other text.
                """
                
                payload = {
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [
                        {"role": "system", "content": "You are Zohra AI's Database Analyst. Output ONLY standard SQLite statement. No explanation, no backticks, no markdown formatting."},
                        {"role": "user", "content": sql_prompt}
                    ],
                    "temperature": 0.1
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                response.raise_for_status()
                sql_resp = response.json()["choices"][0]["message"]["content"].strip()
                sql = sql_resp.replace("```sql", "").replace("```", "").replace("`", "").strip()
                
                data_summary = self._read_analysis_query(sql)
                
                # Synthesize explanation
                summary_prompt = f"""
                You are Zohra AI. Summarize the query results in a clear, professional, direct plain English explanation.
                User request: "{query}"
                SQL executed: "{sql}"
                Query results (JSON format):
                ```json
                {json.dumps(data_summary[:10], indent=2)}
                ```
                Provide a short quantitative summary. Never make up numbers not present in the results. If no records are found, say 'I do not have enough data.'
                """
                
                payload_summary = {
                    "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
                    "messages": [
                        {"role": "system", "content": "You are Zohra AI. Summarize the query results in a clear, professional, direct plain English explanation."},
                        {"role": "user", "content": summary_prompt}
                    ],
                    "temperature": 0.3
                }
                
                response_sum = requests.post(url, headers=headers, json=payload_summary, timeout=10)
                response_sum.raise_for_status()
                summary_resp = response_sum.json()["choices"][0]["message"]["content"].strip()
                return summary_resp
            except Exception as e:
                logger.warning(f"Groq SQL routing failed: {e}. Falling back to pattern-based router.")
        


        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if "why did you buy" in q:
                # Extract symbol
                symbol = "EURUSD"
                for sym in ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "XAGUSD"]:
                    if sym.lower() in q:
                        symbol = sym
                        break
                cursor.execute("""
                    SELECT timestamp_open, entry_price, reason_for_entry, confidence_score
                    FROM trades
                    WHERE symbol = ? AND direction = 'LONG'
                    ORDER BY timestamp_open DESC LIMIT 1
                """, (symbol,))
                row = cursor.fetchone()
                if row:
                    return f"I bought {symbol} at price {row['entry_price']} on {row['timestamp_open'].replace('T', ' ')[:16]}. Reason: {row['reason_for_entry']} (Confidence score: {row['confidence_score']})."
                return f"No buy trades found in my execution history for {symbol}."

            elif "best pair" in q or "best symbol" in q:
                cursor.execute("""
                    SELECT symbol, SUM(pnl_usd) as pnl, COUNT(*) as cnt
                    FROM trades
                    WHERE timestamp_close IS NOT NULL
                    GROUP BY symbol ORDER BY pnl DESC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    return f"The best performing pair is {row['symbol']} with a total net profit of ${row['pnl']:.2f} across {row['cnt']} trades."
                return "Not enough trading history to determine the best pair yet."

            elif "worst strategy" in q or "losing strategy" in q:
                cursor.execute("""
                    SELECT strategy_used, SUM(pnl_usd) as pnl
                    FROM trades
                    WHERE timestamp_close IS NOT NULL
                    GROUP BY strategy_used ORDER BY pnl ASC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    return f"The strategy with the lowest performance is {row['strategy_used']} yielding a net P&L of ${row['pnl']:.2f}."
                return "No strategy metrics compiled yet."

            elif "losing setup" in q or "worst pair" in q:
                cursor.execute("""
                    SELECT symbol, SUM(pnl_usd) as pnl
                    FROM trades
                    WHERE timestamp_close IS NOT NULL
                    GROUP BY symbol ORDER BY pnl ASC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    return f"The worst performing pair is {row['symbol']} with a net P&L of ${row['pnl']:.2f}."
                return "No performance history available."

            elif "highest confidence" in q or "best score" in q:
                cursor.execute("""
                    SELECT symbol, direction, entry_price, confidence_score, pnl_usd
                    FROM trades
                    ORDER BY confidence_score DESC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    res = "win" if row['pnl_usd'] > 0 else "loss"
                    return f"My highest confidence setup was {row['symbol']} {row['direction']} with a score of {row['confidence_score']}. It resulted in a {res} (${row['pnl_usd']:.2f})."
                return "No execution records."

            elif "rejected" in q or "rejections" in q:
                cursor.execute("SELECT COUNT(*) as cnt FROM rejected_trades")
                count = cursor.fetchone()['cnt']
                return f"There are {count} recorded rejected opportunities across all stored history."

            else:
                return "I processed your request but could not find a matching database filter. Ask me: 'Why did you buy EURUSD?', 'Show best pair this week', or 'Show worst strategy'."
        
        except Exception as e:
            return f"An error occurred while querying my memory databases: {str(e)}"
        finally:
            conn.close()

    # ════════════════════════════════════════════════
    #  ADDITIONAL REQS: BACKTEST & SCENARIO SIMULATOR
    # ════════════════════════════════════════════════
    def run_monte_carlo_analysis(self) -> Dict[str, Any]:
        """Performs a Monte Carlo resample analysis on historical closed trades."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT pnl_usd FROM trades WHERE timestamp_close IS NOT NULL")
        rows = cursor.fetchall()
        conn.close()
        
        returns = [r['pnl_usd'] for r in rows if r['pnl_usd'] is not None]
        if len(returns) < 5:
            return {"status": "insufficient_data", "sample_paths": [],
                    "ruin_probability_pct": None, "expected_pnl_30d": None,
                    "reason": "At least five recorded closed trades are required"}

        runs = 1000
        horizon = 30
        simulated_paths = []
        for _ in range(5): # return 5 representative sample paths for front-end charts
            path = [150.0]
            for _ in range(horizon):
                path.append(round(path[-1] + random.choice(returns), 2))
            simulated_paths.append(path)

        # Risk parameters
        ruin_probability = 0.0
        final_values = []
        for _ in range(runs):
            eq = 150.0
            bankrupt = False
            for _ in range(horizon):
                eq += random.choice(returns)
                if eq <= 100.0: # safety stop limit
                    bankrupt = True
            if bankrupt:
                ruin_probability += 1.0
            final_values.append(eq)

        return {
            "sample_paths": simulated_paths,
            "status": "simulation",
            "assumptions": {"starting_equity": 150.0, "stop_equity": 100.0,
                            "trade_horizon": horizon, "runs": runs,
                            "source": "Recorded closed-trade P&L resampling"},
            "ruin_probability_pct": round((ruin_probability / runs) * 100, 2),
            "expected_pnl_30d": round(sum(final_values) / len(final_values) - 150.0, 2)
        }

    def simulate_risk_scenarios(self, lot_mult: float = 1.0, stop_equity: float = 100.0, disable_usd_jpy: bool = False) -> Dict[str, Any]:
        """Simulates what-if outcomes on position sizing, stop limits, and symbol selections."""
        if not math.isfinite(lot_mult) or not 0 < lot_mult <= 10:
            raise ValueError("lot_mult must be greater than 0 and at most 10")
        if not math.isfinite(stop_equity) or not 0 <= stop_equity < 150:
            raise ValueError("stop_equity must be between 0 and the assumed starting equity of 150")
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol, pnl_usd FROM trades WHERE timestamp_close IS NOT NULL AND pnl_usd IS NOT NULL ORDER BY timestamp_close, rowid")
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return {"status": "insufficient_data", "reason": "No recorded closed trades"}

        original_pnl = 0.0
        simulated_pnl = 0.0
        active_balance = 150.0
        original_peak = simulated_peak = 150.0
        original_drawdown = 0.0
        simulated_drawdown = 0.0
        stopped = False
        processed = 0
        sim_balance = 150.0
        for r in rows:
            pnl = r['pnl_usd']
            original_pnl += pnl
            active_balance += pnl
            original_peak = max(original_peak, active_balance)
            original_drawdown = max(original_drawdown, (original_peak - active_balance) / original_peak * 100)
            if stopped or (disable_usd_jpy and "JPY" in (r['symbol'] or "")):
                continue
            sim_pnl = pnl * lot_mult
            simulated_pnl += sim_pnl
            sim_balance += sim_pnl
            processed += 1
            simulated_peak = max(simulated_peak, sim_balance)
            simulated_drawdown = max(simulated_drawdown, (simulated_peak - sim_balance) / simulated_peak * 100)
            # A stop prevents subsequent trades; it cannot undo a recorded loss.
            if sim_balance <= stop_equity:
                stopped = True

        return {
            "status": "simulation",
            "assumptions": {"starting_equity": 150.0, "stop_equity": stop_equity,
                            "lot_multiplier": lot_mult, "exclude_jpy": disable_usd_jpy,
                            "source": "Chronological closed-trade P&L; no spread or margin model"},
            "simulated_trades": processed,
            "stopped": stopped,
            "ending_equity": round(sim_balance, 2),
            "original_net_profit": round(original_pnl, 2),
            "simulated_net_profit": round(simulated_pnl, 2),
            "original_drawdown_pct": round(original_drawdown, 2),
            "simulated_drawdown_pct": round(simulated_drawdown, 2),
            "margin_level_impact": None
        }
