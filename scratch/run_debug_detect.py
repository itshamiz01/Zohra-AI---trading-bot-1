import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.hie.setup_detection_engine import setup_detection_engine
from zohra.hie.historical_data_engine import historical_data_engine

print("Getting candles for EURUSD H1...")
df = historical_data_engine.get_candles("EURUSD", "H1", limit=100)
print(f"Candles retrieved: {len(df)}")
if not df.empty:
    print("Sample candle:")
    print(df.head(2))
    print("Detecting setups...")
    try:
        setups = setup_detection_engine.detect_setups("EURUSD", "H1", df)
        print(f"Setups detected: {len(setups)}")
        if setups:
            print("Sample setup:", setups[0])
    except Exception as e:
        print(f"Error during detection: {e}")
else:
    print("No candles returned.")
