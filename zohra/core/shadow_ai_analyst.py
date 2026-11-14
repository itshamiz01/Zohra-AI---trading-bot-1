"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — SHADOW AI ANALYST                          ║
║         Virtual vs. Live Decision Performance Audit                  ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.learning.shadow")

class ShadowAIAnalyst:
    """
    Compares the outcomes of live trades against their corresponding
    virtual shadow alternatives to evaluate strategy and risk optimizations.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def analyze_shadow_performance(self, parent_trade_id: str, live_pnl: float) -> Dict[str, Any]:
        report = {
            "parent_trade_id": parent_trade_id,
            "live_pnl_usd": live_pnl,
            "best_alternative": "LIVE",
            "pnl_diff_usd": 0.0,
            "shadow_stats": []
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Fetch shadow trades for this parent
                cursor.execute("""
                    SELECT shadow_type, pnl_usd, result 
                    FROM shadow_trades 
                    WHERE parent_trade_id = ? AND status = 'CLOSED'
                """, (parent_trade_id,))
                shadows = [dict(row) for row in cursor.fetchall()]
                
                if not shadows:
                    return report
                    
                best_pnl = live_pnl
                best_type = "LIVE"
                
                for sh in shadows:
                    sh_type = sh["shadow_type"]
                    sh_pnl = sh["pnl_usd"]
                    sh_result = sh["result"]
                    
                    report["shadow_stats"].append({
                        "type": sh_type,
                        "pnl_usd": sh_pnl,
                        "result": sh_result
                    })
                    
                    if sh_pnl > best_pnl:
                        best_pnl = sh_pnl
                        best_type = sh_type
                        
                report["best_alternative"] = best_type
                report["pnl_diff_usd"] = round(best_pnl - live_pnl, 2)
                
                logger.info(f"👥 Shadow Analyst: Parent trade {parent_trade_id} analyzed. Best choice: {best_type} (Diff: ${report['pnl_diff_usd']:+.2f})")
        except Exception as e:
            logger.error(f"Failed to analyze shadow performance: {e}")
            
        return report

# Singleton
shadow_ai_analyst = ShadowAIAnalyst()
