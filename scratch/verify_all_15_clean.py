import sys
import os
import traceback
import pandas as pd
import numpy as np
import datetime as dt

sys.path.insert(0, r"c:\Users\dell\Desktop\trading_bot")
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from zohra.core.enums import StrategyGroup, StrategyName, MarketRegime
from zohra.core.market_regime import MarketRegimeEngine, RegimeReport
from zohra.engines.strategy_engine import UnifiedStrategyEngine

se = UnifiedStrategyEngine()
se._load_strategies()
strats = se._strategies

def make_df(rows):
    t0 = dt.datetime(2026, 10, 4, 8, 0)
    times = [t0 + dt.timedelta(minutes=5 * i) for i in range(len(rows))]
    opens = [float(r[0]) for r in rows]
    highs = [float(r[1]) for r in rows]
    lows = [float(r[2]) for r in rows]
    closes = [float(r[3]) for r in rows]
    vols = [float(r[4]) for r in rows]
    return pd.DataFrame({
        "time": times, "timestamp": times,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "tick_volume": vols, "volume": vols
    })

test_results = {}

# 1. EMA PULLBACK (Trend)
try:
    strat = strats[StrategyName.EMA_PULLBACK.value]
    np.random.seed(42)
    n = 100
    prices = 2650.0 + np.cumsum(np.random.normal(0.5, 0.15, n))
    df = pd.DataFrame({
        'time': [dt.datetime.now() - dt.timedelta(minutes=5*(n-i)) for i in range(n)],
        'open': prices - 0.2, 'high': prices + 0.6, 'low': prices - 0.4, 'close': prices + 0.3,
        'tick_volume': [1000 + i*10 for i in range(n)]
    })
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=90, adx_value=30.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["ema_pullback"] = sig
except Exception as e:
    test_results["ema_pullback"] = str(e)

# 2. FIBONACCI PULLBACK (Trend)
try:
    strat = strats[StrategyName.FIBONACCI_PULLBACK.value]
    # Build 40 bars: 20 base at 2640, then impulse to 2660 (20 pts), then pullback to 2650 (50% fib) with rejection
    rows = []
    for i in range(25):
        rows.append((2640.0, 2640.4, 2639.6, 2640.0, 1000))
    # Impulse from 2640 to 2660
    for i in range(10):
        p = 2640.0 + (i + 1) * 2.0
        rows.append((p - 2.0, p + 0.3, p - 2.1, p, 2000))
    # Retrace to 2650 (50% level of 2640->2660)
    rows.append((2660.0, 2660.2, 2654.0, 2655.0, 1200))
    rows.append((2655.0, 2655.2, 2650.0, 2651.0, 1500))
    # Bullish rejection at 2650 with long lower wick
    rows.append((2651.0, 2653.0, 2649.8, 2652.5, 2500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=88, adx_value=28.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["fibonacci_pullback"] = sig
except Exception as e:
    test_results["fibonacci_pullback"] = str(e)

# 3. MTF ALIGNMENT (Trend)
try:
    strat = strats[StrategyName.MTF_ALIGNMENT.value]
    rows = []
    p = 2650.0
    for i in range(70):
        p += 0.4
        rows.append((p - 0.4, p + 0.3, p - 0.5, p, 1000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=90, adx_value=32.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["mtf_alignment"] = sig
except Exception as e:
    test_results["mtf_alignment"] = str(e)

# 4. MOMENTUM CONTINUATION (Trend)
try:
    strat = strats[StrategyName.MOMENTUM_CONTINUATION.value]
    rows = []
    p = 2650.0
    for i in range(50):
        p += 0.3
        rows.append((p - 0.3, p + 0.2, p - 0.4, p, 1000))
    # Impulsive large bull candle
    rows.append((p, p + 2.5, p - 0.1, p + 2.4, 3000))
    p += 2.4
    # Shallow pullback
    rows.append((p, p + 0.2, p - 0.4, p - 0.2, 1200))
    p -= 0.2
    # Continuation trigger
    rows.append((p, p + 1.2, p - 0.1, p + 1.1, 2500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=88, adx_value=30.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["momentum_continuation"] = sig
except Exception as e:
    test_results["momentum_continuation"] = str(e)

# 5. VWAP MEAN REVERSION (Mean Reversion)
try:
    strat = strats[StrategyName.VWAP_MEAN_REVERSION.value]
    rows = []
    # Flat VWAP anchor at 2650
    for i in range(40):
        rows.append((2650.0, 2650.5, 2649.5, 2650.0, 5000))
    # Stretch far down to 2638 (> 1.5 ATR where ATR is ~0.8)
    rows.append((2650.0, 2650.0, 2640.0, 2640.5, 1000))
    # Rejection candle at 2639 with strong close back towards 2650
    rows.append((2640.5, 2643.5, 2639.0, 2643.0, 2000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.RANGING, confidence=80, adx_value=15.0, ema_alignment="NEUTRAL", reasons=["Range"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["vwap_mean_reversion"] = sig
except Exception as e:
    test_results["vwap_mean_reversion"] = str(e)

# 6. BOLLINGER RSI (Mean Reversion)
try:
    strat = strats[StrategyName.BOLLINGER_RSI.value]
    rows = []
    for i in range(40):
        p = 2650.0 + np.sin(i * 0.5) * 1.0
        rows.append((p, p + 0.4, p - 0.4, p, 1000))
    rows.append((2648.0, 2648.2, 2643.0, 2643.5, 2000))
    rows.append((2643.5, 2644.0, 2641.0, 2641.5, 2500))
    rows.append((2641.5, 2645.0, 2641.2, 2644.8, 3000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.RANGING, confidence=80, adx_value=17.0, ema_alignment="NEUTRAL", reasons=["Range"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["bollinger_rsi"] = sig
except Exception as e:
    test_results["bollinger_rsi"] = str(e)

# 7. SUPPORT RESISTANCE (Mean Reversion)
try:
    strat = strats[StrategyName.SR_REJECTION.value]
    rows = []
    for i in range(20):
        rows.append((2645.0, 2648.0, 2644.0, 2646.0, 1000))
    rows.append((2646.0, 2646.5, 2640.0, 2645.0, 1500))
    for i in range(15):
        rows.append((2645.0, 2649.0, 2644.0, 2647.0, 1000))
    rows.append((2647.0, 2647.5, 2640.1, 2645.5, 1600))
    for i in range(15):
        rows.append((2645.0, 2648.0, 2643.0, 2646.0, 1000))
    rows.append((2644.0, 2645.0, 2640.0, 2644.5, 2500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.RANGING, confidence=85, adx_value=16.0, ema_alignment="NEUTRAL", reasons=["Range"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["sr_rejection"] = sig
except Exception as e:
    test_results["sr_rejection"] = str(e)

# 8. FALSE BREAKOUT (Structure/SMC)
try:
    strat = strats[StrategyName.FALSE_BREAKOUT.value]
    rows = []
    for i in range(40):
        p = 2650.0 + np.sin(i * 0.4) * 4.0
        rows.append((p, p + 0.5, p - 0.5, p, 1000))
    rows.append((2646.0, 2646.5, 2643.0, 2643.5, 2000))
    rows.append((2643.5, 2647.0, 2643.2, 2646.5, 3000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.RANGING, confidence=80, adx_value=18.0, ema_alignment="NEUTRAL", reasons=["Range"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["false_breakout"] = sig
except Exception as e:
    test_results["false_breakout"] = str(e)

# 9. LIQUIDITY MSS (Structure/SMC)
try:
    strat = strats[StrategyName.LIQUIDITY_MSS.value]
    # Look at liquidity_mss evaluate requirements:
    # Needs swing points detected, sweep of low, and market structure shift
    rows = []
    # 35 bars
    for i in range(20):
        rows.append((2650.0, 2652.0, 2649.0, 2650.5, 1000))
    # Swing low
    rows.append((2650.0, 2650.5, 2644.0, 2646.0, 1500))
    # Intermediate rally to swing high
    rows.append((2646.0, 2652.0, 2645.5, 2651.0, 1200))
    # Sweep below swing low (to 2643.0) and reclaim
    rows.append((2651.0, 2651.5, 2643.0, 2645.5, 2500))
    # MSS bar closing above intermediate swing high (2652.0)
    rows.append((2645.5, 2653.5, 2645.0, 2653.0, 3500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.RANGING, confidence=85, adx_value=20.0, ema_alignment="NEUTRAL", reasons=["Range"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["liquidity_mss"] = sig
except Exception as e:
    test_results["liquidity_mss"] = str(e)

# 10. SUPPLY DEMAND (Structure/SMC)
try:
    strat = strats[StrategyName.SUPPLY_DEMAND.value]
    rows = []
    for i in range(25):
        rows.append((2640.0, 2641.0, 2639.0, 2640.0, 1000))
    # Strong rally away (displacement)
    for i in range(4):
        rows.append((2640.0 + i*4, 2640.0 + (i+1)*4 + 0.5, 2640.0 + i*4 - 0.2, 2640.0 + (i+1)*4, 3000))
    # Pull back to demand zone (2640.0)
    rows.append((2656.0, 2656.5, 2648.0, 2649.0, 1200))
    rows.append((2649.0, 2649.5, 2641.0, 2642.5, 2000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=85, adx_value=25.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["supply_demand"] = sig
except Exception as e:
    test_results["supply_demand"] = str(e)

# 11. FVG RETRACEMENT (Structure/SMC)
try:
    strat = strats[StrategyName.FVG_RETRACEMENT.value]
    rows = []
    for i in range(30):
        rows.append((2640.0, 2641.0, 2639.0, 2640.0, 1000))
    rows.append((2640.0, 2642.0, 2639.5, 2641.5, 1500))
    rows.append((2641.5, 2650.5, 2641.0, 2650.0, 4000))
    rows.append((2650.0, 2654.0, 2646.0, 2653.0, 2500))
    rows.append((2653.0, 2653.5, 2647.0, 2648.0, 1200))
    rows.append((2648.0, 2649.0, 2644.0, 2647.5, 2800))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=85, adx_value=26.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["fvg_retracement"] = sig
except Exception as e:
    test_results["fvg_retracement"] = str(e)

# 12. ORDER BLOCK (Structure/SMC)
try:
    strat = strats[StrategyName.ORDER_BLOCK.value]
    rows = []
    for i in range(35):
        rows.append((2645.0, 2645.5, 2644.5, 2645.0, 1000))
    # Down candle before displacement
    rows.append((2645.0, 2645.2, 2642.0, 2642.2, 1200)) # OB: low 2642.0, high 2645.2
    # Huge multi-bar bullish impulse (> 1.2 ATR)
    rows.append((2642.2, 2648.0, 2642.0, 2647.5, 4000))
    rows.append((2647.5, 2653.0, 2647.0, 2652.5, 3500))
    # Retest back down into OB zone [2642.0, 2645.2]
    rows.append((2652.5, 2653.0, 2645.0, 2646.0, 1500))
    # Tap 2644.0 inside OB and reject bullishly
    rows.append((2646.0, 2646.5, 2643.5, 2645.5, 2500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.TRENDING_UP, confidence=85, adx_value=26.0, ema_alignment="BULLISH", reasons=["Trend"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["order_block"] = sig
except Exception as e:
    test_results["order_block"] = str(e)

# 13. BREAKOUT (Breakout/Volatility)
try:
    strat = strats[StrategyName.BREAKOUT.value]
    rows = []
    # 40 bars baseline to establish ATR and Donchian channel
    for i in range(35):
        rows.append((2647.0, 2649.0, 2645.0, 2647.0, 1000))
    # Breakout candle: closes high above donchian high (2649.0) with strong body
    rows.append((2648.0, 2656.0, 2647.5, 2655.0, 3500))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.BREAKOUT_EXPANSION, confidence=90, adx_value=28.0, ema_alignment="BULLISH", reasons=["Breakout"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["breakout"] = sig
except Exception as e:
    test_results["breakout"] = str(e)

# 14. VOLUME BREAKOUT (Breakout/Volatility)
try:
    strat = strats[StrategyName.VOLUME_BREAKOUT.value]
    rows = []
    for i in range(25):
        rows.append((2646.0, 2649.0, 2645.5, 2647.0, 1000))
    rows.append((2647.0, 2653.5, 2646.5, 2653.0, 4000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.BREAKOUT_EXPANSION, confidence=88, adx_value=26.0, ema_alignment="BULLISH", reasons=["Breakout"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["volume_breakout"] = sig
except Exception as e:
    test_results["volume_breakout"] = str(e)

# 15. ATR EXPANSION (Breakout/Volatility)
try:
    strat = strats[StrategyName.ATR_EXPANSION.value]
    rows = []
    # 40 baseline bars so rolling(20) on rolling(14) has full data
    for i in range(35):
        rows.append((2645.0, 2648.0, 2642.0, 2645.0, 1500))
    # 6 bars tight compression
    for i in range(6):
        rows.append((2645.0, 2645.2, 2644.8, 2645.0, 600))
    # Massive expansion candle
    rows.append((2645.0, 2652.0, 2644.8, 2651.5, 4000))
    df = make_df(rows)
    reg = RegimeReport(regime=MarketRegime.BREAKOUT_EXPANSION, confidence=88, adx_value=26.0, ema_alignment="BULLISH", reasons=["Breakout"])
    sig = strat.evaluate(df, df, reg, current_spread_pips=1.5)
    test_results["atr_expansion"] = sig
except Exception as e:
    test_results["atr_expansion"] = str(e)

print("=" * 80)
print(f"{'STRATEGY NAME':<24} | {'STATUS':<8} | {'DETAILS':<44}")
print("=" * 80)
for name, res in test_results.items():
    if hasattr(res, 'direction'):
        print(f"{name:<24} | \u2705 PASS   | Signal: {res.direction} @ {res.entry_price:.2f} (SL={res.stop_loss:.2f}, TP={res.take_profit:.2f})")
    elif res is None:
        print(f"{name:<24} | \u26a0\ufe0f FILTER | Logic evaluated cleanly without error (no signal on synthetic data)")
    else:
        print(f"{name:<24} | \u274c ERROR  | {str(res)[:44]}")
print("=" * 80)
