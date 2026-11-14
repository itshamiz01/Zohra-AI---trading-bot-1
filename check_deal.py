import MetaTrader5 as mt5
import datetime as dt
import sys
import os
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
MT5_TERMINAL_PATH = os.getenv("MT5_TERMINAL_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

init_ok = mt5.initialize(path=MT5_TERMINAL_PATH) if MT5_TERMINAL_PATH else mt5.initialize()
if not init_ok:
    print("Failed to initialize MT5:", mt5.last_error())
    sys.exit(1)

ticket = 56994896218
deals = mt5.history_deals_get(position=ticket)
if deals:
    print(f"Deals for position {ticket}:")
    for deal in deals:
        print(f"  Deal Ticket: {deal.ticket}")
        print(f"  Symbol: {deal.symbol}")
        print(f"  Volume: {deal.volume}")
        print(f"  Price: {deal.price}")
        print(f"  Profit: {deal.profit}")
        print(f"  Commission: {deal.commission}")
        print(f"  Swap: {deal.swap}")
        print(f"  Type (0=Buy, 1=Sell): {deal.type}")
        print(f"  Entry (0=In, 1=Out, 2=InOut): {deal.entry}")
        print(f"  Comment: {deal.comment}")
else:
    print(f"No deals found for position/ticket {ticket} directly.")
    # Search by time
    from_date = dt.datetime.now() - dt.timedelta(hours=2)
    to_date = dt.datetime.now() + dt.timedelta(minutes=10)
    history_deals = mt5.history_deals_get(from_date, to_date)
    if history_deals:
        print("Recent history deals:")
        for deal in history_deals[-10:]:
            print(f"  Ticket: {deal.ticket} | Pos: {deal.position_id} | Sym: {deal.symbol} | Vol: {deal.volume} | Price: {deal.price} | Profit: {deal.profit} | Comm: {deal.commission} | Swap: {deal.swap} | Entry: {deal.entry} | Type: {deal.type}")

mt5.shutdown()
