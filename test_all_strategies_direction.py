import pandas as pd
import numpy as np
import datetime
from zohra.core.market_regime import MarketRegime, market_regime_engine
from zohra.engines.strategy_engine import UnifiedStrategyEngine

print("=== TESTING ALL 15 STRATEGIES FOR DIRECTION & SL/TP INTEGRITY ===")

# Create synthetic bullish data
np.random.seed(42)
n = 100
bull_prices = 4300.0 + np.cumsum(np.random.normal(0.5, 0.2, n))
bull_df = pd.DataFrame({
    'time': [datetime.datetime.now() - datetime.timedelta(minutes=5*(n-i)) for i in range(n)],
    'open': bull_prices - 0.2,
    'high': bull_prices + 0.6,
    'low': bull_prices - 0.4,
    'close': bull_prices + 0.3,
    'tick_volume': [1000 + i*10 for i in range(n)]
})

# Create synthetic bearish data
bear_prices = 4350.0 - np.cumsum(np.random.normal(0.5, 0.2, n))
bear_df = pd.DataFrame({
    'time': [datetime.datetime.now() - datetime.timedelta(minutes=5*(n-i)) for i in range(n)],
    'open': bear_prices + 0.2,
    'high': bear_prices + 0.4,
    'low': bear_prices - 0.6,
    'close': bear_prices - 0.3,
    'tick_volume': [1000 + i*10 for i in range(n)]
})

regime_bull = market_regime_engine.classify_regime(bull_df, bull_df)
regime_bear = market_regime_engine.classify_regime(bear_df, bear_df)

print(f"Bullish classified as: {regime_bull.regime.value} (conf={regime_bull.confidence})")
print(f"Bearish classified as: {regime_bear.regime.value} (conf={regime_bear.confidence})")

se = UnifiedStrategyEngine()
se._load_strategies()

errors = []
for name, strat in se._strategies.items():
    print(f"\nEvaluating: {name} ({strat.__class__.__name__})")
    for r_name, df, reg in [("BULLISH", bull_df, regime_bull), ("BEARISH", bear_df, regime_bear)]:
        try:
            sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
            if sig:
                print(f"  [{r_name}] -> Signal: {sig.direction} @ {sig.entry_price} | SL={sig.stop_loss} | TP={sig.take_profit}")
                # Direction check
                if r_name == "BULLISH" and sig.direction != "BUY":
                    msg = f"  ❌ MISMATCH: {name} gave {sig.direction} in BULLISH regime!"
                    print(msg)
                    errors.append(msg)
                elif r_name == "BEARISH" and sig.direction != "SELL":
                    msg = f"  ❌ MISMATCH: {name} gave {sig.direction} in BEARISH regime!"
                    print(msg)
                    errors.append(msg)
                
                # SL/TP side checks
                if sig.direction == "BUY":
                    if not (sig.stop_loss < sig.entry_price < sig.take_profit):
                        msg = f"  ❌ SL/TP INVALID FOR BUY: SL={sig.stop_loss}, Entry={sig.entry_price}, TP={sig.take_profit}"
                        print(msg)
                        errors.append(msg)
                elif sig.direction == "SELL":
                    if not (sig.stop_loss > sig.entry_price > sig.take_profit):
                        msg = f"  ❌ SL/TP INVALID FOR SELL: SL={sig.stop_loss}, Entry={sig.entry_price}, TP={sig.take_profit}"
                        print(msg)
                        errors.append(msg)
            else:
                print(f"  [{r_name}] -> No signal (Neutral / Filtered)")
        except Exception as e:
            msg = f"  ❌ EXCEPTION in {name} ({r_name}): {e}"
            print(msg)
            errors.append(msg)

print("\n" + "="*60)
if errors:
    print(f"FAILED WITH {len(errors)} ANOMALIES:")
    for err in errors:
        print(err)
else:
    print("ALL TESTED STRATEGIES PASSED DIRECTION AND SL/TP VALIDATION!")
print("="*60)
