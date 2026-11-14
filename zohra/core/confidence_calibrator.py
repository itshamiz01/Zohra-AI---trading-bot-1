"""
╔══════════════════════════════════════════════════════════════════════╗
║                 ZOHRA — CONFIDENCE CALIBRATION ENGINE                ║
║         Statistical Validation of Predicted vs. Actual Win Rates     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import sqlite3
import logging
from typing import Dict, List, Any
from zohra.config.settings import DB_PATH

logger = logging.getLogger("zohra.learning.calibration")

class ConfidenceCalibrator:
    """
    Groups historical trades into confidence score bins (e.g. 70-79, 80-89, 90-100)
    and evaluates predicted win rate vs. actual win rate to detect overconfidence drift.
    """
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def calibrate_confidence_scores(self) -> Dict[str, Any]:
        calibration_report = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Fetch all closed trades
                cursor.execute("""
                    SELECT confidence_score, pnl_usd 
                    FROM trades 
                    WHERE exit_price IS NOT NULL AND pnl_usd IS NOT NULL
                """)
                trades = [dict(row) for row in cursor.fetchall()]
                
                # Bins: 70-79, 80-89, 90-100
                bins = {
                    "70-79": {"total": 0, "wins": 0, "predicted_win_rate": 75.0},
                    "80-89": {"total": 0, "wins": 0, "predicted_win_rate": 85.0},
                    "90-100": {"total": 0, "wins": 0, "predicted_win_rate": 95.0}
                }
                
                for t in trades:
                    score = t["confidence_score"]
                    pnl = t["pnl_usd"]
                    is_win = pnl > 0
                    
                    if 70 <= score < 80:
                        bin_name = "70-79"
                    elif 80 <= score < 90:
                        bin_name = "80-89"
                    elif 90 <= score <= 100:
                        bin_name = "90-100"
                    else:
                        continue
                        
                    bins[bin_name]["total"] += 1
                    if is_win:
                        bins[bin_name]["wins"] += 1
                
                # Calculate actual win rate and drift per bin
                for name, data in bins.items():
                    total = data["total"]
                    wins = data["wins"]
                    actual_wr = (wins / total * 100.0) if total > 0 else 0.0
                    drift = actual_wr - data["predicted_win_rate"]
                    
                    calibration_report[name] = {
                        "total_trades": total,
                        "wins": wins,
                        "predicted_win_rate_pct": data["predicted_win_rate"],
                        "actual_win_rate_pct": round(actual_wr, 1),
                        "drift_pct": round(drift, 1),
                        "status": "CALIBRATED" if abs(drift) <= 10 else "OVERCONFIDENT" if drift < -10 else "UNDERCONFIDENT"
                    }
        except Exception as e:
            logger.error(f"Failed to calibrate confidence: {e}")
            
        return calibration_report

# Singleton
confidence_calibrator = ConfidenceCalibrator()
