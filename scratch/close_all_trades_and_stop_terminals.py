import os
import sys
import time
import subprocess
import MetaTrader5 as mt5

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from zohra.config.settings import ACTIVE_ACCOUNT_CONFIGS

def close_single_position(p):
    """Close a single position on the currently connected MT5 instance."""
    symbol = p.symbol
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return False, "No tick data"

    close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == 0 else tick.ask

    info = mt5.symbol_info(symbol)
    filling_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
    
    # Try preferred filling first based on symbol info
    if info:
        fm = info.filling_mode
        ordered_modes = []
        if fm & 1:
            ordered_modes.append(mt5.ORDER_FILLING_FOK)
        if fm & 2:
            ordered_modes.append(mt5.ORDER_FILLING_IOC)
        if fm & 4:
            ordered_modes.append(mt5.ORDER_FILLING_RETURN)
        for m in filling_modes:
            if m not in ordered_modes:
                ordered_modes.append(m)
        filling_modes = ordered_modes

    last_error_str = ""
    for filling in filling_modes:
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": p.volume,
            "type": close_type,
            "position": p.ticket,
            "price": price,
            "deviation": 30,
            "magic": p.magic,
            "comment": "EmergencyClose",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            return True, f"Closed at {res.price}"
        elif res:
            last_error_str = f"retcode={res.retcode} ({res.comment})"
        else:
            last_error_str = f"mt5 error: {mt5.last_error()}"
    return False, last_error_str


def process_all_accounts():
    summary = []
    
    for acc in ACTIVE_ACCOUNT_CONFIGS:
        print(f"\n=======================================================")
        print(f"Connecting to {acc.account_id} ({acc.name}) | Login: {acc.login}")
        print(f"=======================================================")
        mt5.shutdown()
        time.sleep(0.5)
        
        init_res = mt5.initialize(
            path=acc.terminal_path,
            login=acc.login,
            password=acc.password,
            server=acc.server,
        )
        if not init_res:
            init_res = mt5.initialize(path=acc.terminal_path)
            
        if not init_res:
            print(f"❌ Failed to connect to {acc.account_id}: {mt5.last_error()}")
            summary.append((acc.account_id, "CONNECT_FAILED", 0, 0))
            continue

        info = mt5.account_info()
        if not info:
            print(f"❌ Cannot fetch account info: {mt5.last_error()}")
            summary.append((acc.account_id, "INFO_FAILED", 0, 0))
            continue
            
        print(f"✅ Connected to Login #{info.login} ({info.server}) | Balance: ${info.balance:.2f} | Equity: ${info.equity:.2f}")

        positions = mt5.positions_get()
        if positions is None or len(positions) == 0:
            print("✨ No open positions found on this account.")
            summary.append((acc.account_id, "OK", 0, 0))
            continue

        print(f"Found {len(positions)} open position(s). Closing now...")
        closed_count = 0
        failed_count = 0
        
        for pos in positions:
            ptype = "BUY" if pos.type == 0 else "SELL"
            print(f"  Closing #{pos.ticket} | {pos.symbol} {ptype} {pos.volume} lots | Profit: ${pos.profit:.2f} ... ", end="")
            success, msg = close_single_position(pos)
            if success:
                print(f"✅ {msg}")
                closed_count += 1
            else:
                print(f"❌ Failed: {msg}")
                failed_count += 1

        # Re-verify remaining positions
        time.sleep(1)
        remaining = mt5.positions_get()
        rem_count = len(remaining) if remaining else 0
        if rem_count == 0:
            print(f"🎉 All {closed_count} positions successfully CLOSED on {acc.account_id}!")
        else:
            print(f"⚠️ Warning: {rem_count} position(s) still open on {acc.account_id}!")

        summary.append((acc.account_id, "CLOSED", closed_count, rem_count))

    mt5.shutdown()
    print("\n=======================================================")
    print("TRADE CLOSURE SUMMARY:")
    for acc_id, status, closed, rem in summary:
        print(f"  {acc_id}: Status={status} | Closed={closed} | Remaining={rem}")
    print("=======================================================\n")


if __name__ == "__main__":
    process_all_accounts()
