import sqlite3
import os

db_files = [
    "logs/zohra_trades_a.db",
    "logs/zohra_trades.db",
    "logs/trades.db",
    "logs/zohra.db"
]

for db in db_files:
    if not os.path.exists(db):
        print(f"File not found: {db}")
        continue
    print(f"\n========================================\nDATABASE: {db}\n========================================")
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables: {tables}")
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [f"{col[1]} ({col[2]})" for col in cursor.fetchall()]
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"  Table '{table}': {count} rows")
            print(f"    Columns: {', '.join(columns)}")
            
            # Show a sample row if any
            if count > 0:
                cursor.execute(f"SELECT * FROM {table} LIMIT 1;")
                sample = cursor.fetchone()
                print(f"    Sample: {sample}")
    except Exception as e:
        print(f"  Error: {e}")
