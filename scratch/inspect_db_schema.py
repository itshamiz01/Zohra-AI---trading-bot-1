import sqlite3, os
import sys
sys.stdout.reconfigure(encoding='utf-8')

dbs = [
    r'logs\hie_data.db',
    r'logs\zohra_trades_a.db',
    r'logs\zohra_trades.db',
    r'logs\chroma_db_a\chroma.sqlite3'
]

for db_file in dbs:
    if os.path.exists(db_file):
        print(f"\n=== {db_file} ===")
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables[:15]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {t}")
                print(f"  {t}: {cur.fetchone()[0]:,} rows")
            except Exception as e:
                print(f"  {t}: {e}")
