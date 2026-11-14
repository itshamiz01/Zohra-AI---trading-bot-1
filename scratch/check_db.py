import sqlite3
import os

db_path = "logs/hie_data.db"
print(f"Checking DB: {db_path} (exists: {os.path.exists(db_path)})")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    tables = [
        "hie_candles",
        "hie_setups",
        "hie_setup_outcomes",
        "hie_pattern_stats",
        "hie_market_memory",
        "hie_symbol_profiles",
        "hie_confidence_calibration",
        "hie_similarity_cache"
    ]
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = cursor.fetchone()[0]
            print(f"Table {t}: {cnt} rows")
        except Exception as e:
            print(f"Table {t} error: {e}")
    conn.close()
