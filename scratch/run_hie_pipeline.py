import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.hie.setup_detection_engine import setup_detection_engine
from zohra.hie.outcome_analysis_engine import outcome_analysis_engine
from zohra.hie.historical_pattern_database import historical_pattern_database
from zohra.hie.market_memory_engine import market_memory_engine
from zohra.hie.symbol_intelligence_profiles import symbol_intelligence_profiles
from zohra.hie.failure_pattern_detector import failure_pattern_detector
from zohra.hie.confidence_calibration_engine import confidence_calibration_engine
from zohra.hie.historical_data_engine import HIE_SYMBOLS
import sqlite3

# Initialize cache table in hie_data.db just in case
try:
    conn = sqlite3.connect("logs/hie_data.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hie_similarity_cache (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            query_hash   TEXT UNIQUE NOT NULL,
            result_json  TEXT NOT NULL,
            cached_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    print("Created similarity cache table in hie_data.db")
except Exception as e:
    print(f"Error creating cache table: {e}")

timeframes = ["M15", "H1", "H4"]

print("Starting Setup Detection...")
for symbol in HIE_SYMBOLS:
    for tf in timeframes:
        n = setup_detection_engine.detect_and_store(symbol, tf)
        if n > 0:
            print(f"  Detected {n} setups for {symbol} / {tf}")

print("Starting Outcome Analysis...")
processed = 1
total_processed = 0
while processed > 0:
    processed = outcome_analysis_engine._process_unanalyzed_batch(batch_size=1000)
    total_processed += processed
    if processed > 0:
        print(f"  Processed {processed} outcomes...")
    time.sleep(0.1)

print(f"Total processed outcomes: {total_processed}")

print("Rebuilding Pattern Database Stats...")
rows = historical_pattern_database.rebuild_stats()
print(f"  Rebuilt {rows} pattern rows.")

print("Refreshing Market Memory...")
mem_rows = market_memory_engine.refresh_memory()
print(f"  Refreshed {mem_rows} memory rows.")

print("Rebuilding Symbol Profiles...")
prof_rows = symbol_intelligence_profiles.rebuild_all_profiles()
print(f"  Rebuilt {prof_rows} profiles.")

print("Running Failure Pattern Detector...")
fail_rows = failure_pattern_detector.scan_and_flag()
print(f"  Detected and flagged {fail_rows} failure patterns.")

print("Calibrating Confidence...")
confidence_calibration_engine.calibrate()
print("  Calibration completed.")

print("Pipeline Finished!")
