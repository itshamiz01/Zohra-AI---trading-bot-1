import os
import sqlite3

for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".db"):
            path = os.path.join(root, file)
            try:
                conn = sqlite3.connect(path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                print(f"Path: {path}")
                print(f"  Tables: {tables}")
                for t in tables:
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {t};")
                        count = cursor.fetchone()[0]
                        print(f"    Table '{t}': {count} rows")
                    except Exception:
                        pass
                conn.close()
            except Exception as e:
                print(f"Error for {path}: {e}")
