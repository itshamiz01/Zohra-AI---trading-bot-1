#!/usr/bin/env python3
"""
Read-only MetaApi connection check for Zohra.

Verifies that the cloud MT5 account is reachable through the MetaApi
adapter and prints account state. NEVER places, modifies or closes
any trade — it only reads.

Usage:
    METAAPI_TOKEN=... METAAPI_ACCOUNT_ID=... python scripts/check_metaapi_connection.py

Exit code 0 = connected and reading live data.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.brokers.metaapi_adapter import metaapi_broker


def main() -> int:
    if not os.getenv("METAAPI_TOKEN") or not os.getenv("METAAPI_ACCOUNT_ID"):
        print("ERROR: set METAAPI_TOKEN and METAAPI_ACCOUNT_ID first.")
        return 2
    print("Connecting to MetaApi cloud account (read-only)...")
    if not metaapi_broker.connect():
        print("FAILED: could not connect. Check token, account id and that "
              "the account is deployed in MetaApi.")
        return 1
    info = metaapi_broker.get_account_info() or {}
    print(f"CONNECTED  login={info.get('login')}  server={info.get('server')}")
    print(f"  type={info.get('type')}  currency={info.get('currency')}  "
          f"balance={info.get('balance')}  equity={info.get('equity')}  "
          f"free_margin={info.get('free_margin')}")
    positions = metaapi_broker.get_open_positions()
    print(f"  open positions: {len(positions)}")
    symbols = metaapi_broker.get_symbols()
    print(f"  symbols available: {len(symbols)}")
    if symbols:
        probe = "EURUSD" if "EURUSD" in symbols else symbols[0]
        price = metaapi_broker.get_current_price(probe)
        print(f"  sample price {probe}: bid={price.get('bid')} ask={price.get('ask')}")
        df = metaapi_broker.get_ohlcv(probe, "H1", 5)
        print(f"  H1 candles fetched: {0 if df is None else len(df)}")
    health = metaapi_broker.health_check()
    print(f"  health: connected={health['connected']} "
          f"trading_allowed={health['trading_allowed']} "
          f"(read-only until METAAPI_TRADING_ENABLED=1)")
    metaapi_broker.disconnect()
    print("OK — cloud account is reachable and readable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
