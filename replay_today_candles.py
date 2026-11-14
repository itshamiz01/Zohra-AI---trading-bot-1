import sys
sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
import pandas as pd
import datetime
from zohra.core.market_regime import market_regime_engine
from zohra.engines.strategy_engine import UnifiedStrategyEngine
from zohra.config.settings import ACTIVE_PAIRS

print("=== REPLAYING REAL MARKET CANDLES ACROSS ALL ACTIVE PAIRS ===")

term_a = r"C:\MetaTrader 5 A\terminal64.exe"
if not mt5.initialize(path=term_a):
    print("Failed to connect to MT5:", mt5.last_error())
    exit(1)

se = UnifiedStrategyEngine()
se._load_strategies()

for symbol in ACTIVE_PAIRS:
    print(f"\n{'='*55}\nANALYZING {symbol}\n{'='*55}")
    # Get M5 rates
    rates_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    
    if rates_m5 is None or rates_m15 is None:
        print(f"Could not fetch rates for {symbol}")
        continue
        
    df_m5 = pd.DataFrame(rates_m5)
    df_m5['time'] = pd.to_datetime(df_m5['time'], unit='s')
    
    df_m15 = pd.DataFrame(rates_m15)
    df_m15['time'] = pd.to_datetime(df_m15['time'], unit='s')
    
    # Classime regime
    reg_rep = market_regime_engine.classify_regime(df_m5, df_m15)
    last_close = float(df_m5.iloc[-1]['close'])
    print(f"Current Regime: {reg_rep.regime.value} (Confidence: {reg_rep.confidence}) | Close={last_close}")
    
    # Run all strategies
    signals_found = []
    for name, strat in se._strategies.items():
        try:
            sig = se._run_strategy(name, strat, symbol, reg_rep, df_entry=df_m5, df_htf=df_m15, spread_pips=2.0)
            if sig and sig.get("direction"):
                signals_found.append((name, sig))
                print(f"  ⚡ TRIGGER: [{name}] {sig['direction']} {symbol} Entry={sig['entry']} SL={sig['stop_loss']} TP={sig['take_profit']}")
        except Exception as e:
            print(f"  ❌ Error in {name}: {e}")
            
    if not signals_found:
        print("  (No strategy triggered right now)")
    else:
        buys = [s for s in signals_found if s[1]["direction"] == "BUY"]
        sells = [s for s in signals_found if s[1]["direction"] == "SELL"]
        print(f"  Summary: {len(buys)} BUY vs {len(sells)} SELL")
        if buys and sells:
            print("  🚨 MASSIVE CONFLICT: Both BUY and SELL triggered on same symbol!")
        else:
            winning_dir = "BUY" if buys else "SELL"
            print(f"  ✅ Clean unified consensus: {winning_dir} ({len(buys or sells)} confirmations)")

mt5.shutdown()
