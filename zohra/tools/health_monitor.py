#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — REAL-TIME HEALTH MONITOR                   ║
║          Live Multi-Account & Two-Symbol Diagnostic Tool             ║
╚══════════════════════════════════════════════════════════════════════╝
Usage:
    python -m zohra.tools.health_monitor
    python zohra/tools/health_monitor.py
"""

import os
import sys
import time
import datetime as dt
from dotenv import dotenv_values

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import MetaTrader5 as mt5
    MT5_INSTALLED = True
except ImportError:
    MT5_INSTALLED = False

BOT_CONFIGS = [
    {
        "name": "Bot A",
        "env_path": r"c:\Users\dell\Desktop\trading_bot\.env",
        "log_path": r"c:\Users\dell\Desktop\trading_bot\logs\zohra_brain_a.log",
        "db_path": r"c:\Users\dell\Desktop\trading_bot\logs\zohra_trades_a.db",
    },
    {
        "name": "Bot B",
        "env_path": r"c:\Users\dell\Desktop\Trading Bot 2.0\.env",
        "log_path": r"c:\Users\dell\Desktop\Trading Bot 2.0\logs\zohra_brain_b.log",
        "db_path": r"c:\Users\dell\Desktop\Trading Bot 2.0\logs\zohra_trades_b.db",
    },
    {
        "name": "Bot C",
        "env_path": r"c:\Users\dell\Desktop\Trading Bot 3.0\.env",
        "log_path": r"c:\Users\dell\Desktop\Trading Bot 3.0\logs\zohra_brain_c.log",
        "db_path": r"c:\Users\dell\Desktop\Trading Bot 3.0\logs\zohra_trades_c.db",
    }
]


def audit_account(cfg_dict: dict) -> dict:
    name = cfg_dict["name"]
    env_path = cfg_dict["env_path"]
    res = {
        "name": name,
        "env_exists": os.path.exists(env_path),
        "terminal_connected": False,
        "login": 0,
        "server": "",
        "balance": 0.0,
        "equity": 0.0,
        "trade_allowed": False,
        "algo_allowed": False,
        "xau_ready": False,
        "xau_spread_pts": 0,
        "xau_bid": 0.0,
        "xau_ask": 0.0,
        "xag_ready": False,
        "xag_spread_pts": 0,
        "xag_bid": 0.0,
        "xag_ask": 0.0,
        "open_positions": 0,
    }

    if not res["env_exists"] or not MT5_INSTALLED:
        return res

    cfg = dotenv_values(env_path)
    login = int(cfg.get("MT5_LOGIN", 0) or 0)
    password = cfg.get("MT5_PASSWORD", "")
    server = cfg.get("MT5_SERVER", "")
    terminal_path = cfg.get("MT5_TERMINAL_PATH", "")

    res["login"] = login
    res["server"] = server

    init_ok = False
    if terminal_path and os.path.exists(terminal_path):
        init_ok = mt5.initialize(path=terminal_path)
    else:
        init_ok = mt5.initialize()

    if init_ok:
        if login and password and server:
            mt5.login(login=login, password=password, server=server)

        acc = mt5.account_info()
        term = mt5.terminal_info()

        if acc:
            res["terminal_connected"] = bool(term.connected if term else True)
            res["balance"] = acc.balance
            res["equity"] = acc.equity
            res["trade_allowed"] = acc.trade_allowed
            res["algo_allowed"] = getattr(term, "trade_allowed", False) if term else False

            # XAUUSD check
            mt5.symbol_select("XAUUSD", True)
            s_xau = mt5.symbol_info("XAUUSD")
            t_xau = mt5.symbol_info_tick("XAUUSD")
            if s_xau and t_xau and t_xau.bid > 0:
                res["xau_ready"] = True
                res["xau_spread_pts"] = s_xau.spread
                res["xau_bid"] = t_xau.bid
                res["xau_ask"] = t_xau.ask

            # XAGUSD check
            mt5.symbol_select("XAGUSD", True)
            s_xag = mt5.symbol_info("XAGUSD")
            t_xag = mt5.symbol_info_tick("XAGUSD")
            if s_xag and t_xag and t_xag.bid > 0:
                res["xag_ready"] = True
                res["xag_spread_pts"] = s_xag.spread
                res["xag_bid"] = t_xag.bid
                res["xag_ask"] = t_xag.ask

            positions = mt5.positions_get()
            res["open_positions"] = len(positions) if positions else 0

        mt5.shutdown()

    return res


def print_health_dashboard():
    print("═" * 75)
    print("           ZOHRA MULTI-BOT REAL-TIME SYSTEM HEALTH SUMMARY")
    print(f"               Time: {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("═" * 75)

    for cfg in BOT_CONFIGS:
        report = audit_account(cfg)
        status_icon = "🟢 ONLINE" if report["terminal_connected"] else "🔴 OFFLINE"
        print(f"\n[{report['name']}] Status: {status_icon}")
        print(f"  MT5 Terminal Connected  : {'YES' if report['terminal_connected'] else 'NO'}")
        print(f"  Account Login / Server  : #{report['login']} | {report['server']}")
        print(f"  Balance / Equity        : ${report['balance']:,.2f} / ${report['equity']:,.2f}")
        print(f"  Trade Allowed (Account) : {'✅ YES' if report['trade_allowed'] else '❌ NO'}")
        print(f"  AlgoTrading (Toolbar)   : {'✅ ENABLED' if report['algo_allowed'] else '❌ DISABLED (Press Ctrl+E)'}")
        print(f"  Open Positions          : {report['open_positions']}")
        
        # Gold status
        xau_icon = "✅ READY" if report["xau_ready"] else "❌ NOT READY"
        xau_pips = report['xau_spread_pts'] * 0.1
        print(f"  Gold (XAUUSD)           : {xau_icon} | Spread={report['xau_spread_pts']} pts ({xau_pips:.1f} pips) | Bid={report['xau_bid']} | Ask={report['xau_ask']}")
        print(f"  Silver (XAGUSD)         : 🚫 DISABLED (Gold-Only Trading Mode)")

    print("\n" + "═" * 75)
    print("  ACTIVE TRADING UNIVERSE: Strictly Gold (XAUUSD)")
    print("  ALL OTHER SYMBOLS: DISABLED & GUARDED")
    print("═" * 75 + "\n")


if __name__ == "__main__":
    print_health_dashboard()
