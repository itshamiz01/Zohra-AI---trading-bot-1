"""
╔══════════════════════════════════════════════════════════════════════╗
║           ZOHRA — UNIFIED STRATEGY ENGINE (15 Strategies)           ║
║     Centralized signal generation — account-agnostic                ║
╚══════════════════════════════════════════════════════════════════════╝

This is the BRAIN of the ZOHRA unified trading system.

Contains all 15 strategies:
  TREND Group (4):       ema_pullback, fibonacci_pullback, mtf_alignment, momentum_continuation
  MEAN_REVERSION Group (4): vwap_mean_reversion, bollinger_rsi, sr_rejection, false_breakout
  STRUCTURE_SMC Group (4):  liquidity_mss, supply_demand, fvg_retracement, order_block
  BREAKOUT_VOLATILITY (3):  breakout, volume_breakout, atr_expansion

This process should NEVER:
  - Login to MT5 accounts
  - Calculate account-specific lot sizes
  - Place orders / modify positions / close positions
  - Access account balance or equity

It receives:  MARKET_DATA
It produces:  STRATEGY_SIGNAL
"""

import os
import sys
import uuid
import logging
import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from zohra.core.message_bus import message_bus, ZohraMessage, MessageTopic
from zohra.core.enums import MarketRegime, StrategyName, StrategyGroup
from zohra.config.settings import ACTIVE_PAIRS, TF_H4, TF_H1, TF_M15, TF_M5, LOG_DIR
import json

logger = logging.getLogger("zohra.strategy_engine")


class UnifiedStrategyEngine:
    """
    Centralized 15-Strategy Engine for the ZOHRA unified trading system.

    Runs ALL strategies against market data and produces account-agnostic signals.
    Signals contain: strategy_id, symbol, direction, entry, SL, TP, confidence.
    They do NOT contain: lot sizes, account info, or execution details.
    """

    PROCESS_NAME = "zohra-strategy-engine"

    def __init__(self, market_data_service=None):
        self._market_data = market_data_service
        self._running = False
        self._start_time = 0.0
        self._signal_count = 0

        # Strategy instances (lazy-loaded)
        self._strategies: Dict[str, Any] = {}
        self._strategy_loaded = False

        # Bot profile for strategy filtering
        from zohra.config.bot_profile import load_bot_profile
        self._profile = load_bot_profile("ZOHRA_UNIFIED")

        logger.info(f"UnifiedStrategyEngine initialized | {len(self._profile.enabled_strategies)} strategies enabled")

    # ═══════════════════════════════════════════════════════════
    #  STRATEGY LOADING
    # ═══════════════════════════════════════════════════════════

    def _load_strategies(self):
        """Load all 15 strategy instances."""
        if self._strategy_loaded:
            return

        logger.info("Loading all 15 strategies into unified engine...")

        strategy_class_map = {
            # ─── TREND Group ───
            StrategyName.EMA_PULLBACK.value: ("zohra.strategies.ema_pullback", "EmaPullbackStrategy"),
            StrategyName.FIBONACCI_PULLBACK.value: ("zohra.strategies.fibonacci_pullback", "FibonacciPullbackStrategy"),
            StrategyName.MTF_ALIGNMENT.value: ("zohra.strategies.mtf_alignment", "MtfAlignmentStrategy"),
            StrategyName.MOMENTUM_CONTINUATION.value: ("zohra.strategies.momentum_continuation", "MomentumContinuationStrategy"),

            # ─── MEAN_REVERSION Group ───
            StrategyName.VWAP_MEAN_REVERSION.value: ("zohra.strategies.vwap_mean_reversion", "VwapMeanReversionStrategy"),
            StrategyName.BOLLINGER_RSI.value: ("zohra.strategies.bollinger_rsi", "BollingerRsiStrategy"),
            StrategyName.SR_REJECTION.value: ("zohra.strategies.support_resistance", "SupportResistanceStrategy"),
            StrategyName.FALSE_BREAKOUT.value: ("zohra.strategies.false_breakout", "FalseBreakoutStrategy"),

            # ─── STRUCTURE_SMC Group ───
            StrategyName.LIQUIDITY_MSS.value: ("zohra.strategies.liquidity_mss", "LiquidityMssStrategy"),
            StrategyName.SUPPLY_DEMAND.value: ("zohra.strategies.supply_demand", "SupplyDemandStrategy"),
            StrategyName.FVG_RETRACEMENT.value: ("zohra.strategies.fvg", "FvgRetracementStrategy"),
            StrategyName.ORDER_BLOCK.value: ("zohra.strategies.order_block", "OrderBlockStrategy"),

            # ─── BREAKOUT_VOLATILITY Group ───
            StrategyName.BREAKOUT.value: ("zohra.strategies.breakout", "BreakoutStrategy"),
            StrategyName.VOLUME_BREAKOUT.value: ("zohra.strategies.volume_breakout", "VolumeBreakoutStrategy"),
            StrategyName.ATR_EXPANSION.value: ("zohra.strategies.atr_expansion", "AtrExpansionStrategy"),
        }

        loaded = 0
        for strategy_name in self._profile.enabled_strategies:
            if strategy_name not in strategy_class_map:
                logger.warning(f"Strategy '{strategy_name}' has no module mapping — skipped")
                continue

            module_path, class_name = strategy_class_map[strategy_name]
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name, None)
                if cls is not None:
                    instance = cls()
                    self._strategies[strategy_name] = instance
                    loaded += 1
                    logger.info(f"  ✅ Loaded strategy: {strategy_name} ({class_name})")
                else:
                    # Fallback search for any Strategy class
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, type) and hasattr(attr, 'evaluate') and attr_name != 'BaseStrategy':
                            self._strategies[strategy_name] = attr()
                            loaded += 1
                            logger.info(f"  ✅ Loaded strategy: {strategy_name} ({attr_name})")
                            break
                    else:
                        logger.warning(f"  ⚠️ Could not find strategy class in {module_path}")
            except Exception as e:
                logger.error(f"  ❌ Error loading strategy '{strategy_name}': {e}", exc_info=True)

        self._strategy_loaded = True
        logger.info(f"Strategy loading complete: {loaded}/{len(self._profile.enabled_strategies)} strategies loaded")

    # ═══════════════════════════════════════════════════════════
    #  LIFECYCLE
    # ═══════════════════════════════════════════════════════════

    def start(self):
        """Initialize strategy engine."""
        self._load_strategies()
        self._running = True
        self._start_time = time.time()
        logger.info(f"✅ UnifiedStrategyEngine started with {len(self._strategies)} active strategies")

    def stop(self):
        self._running = False
        logger.info("UnifiedStrategyEngine stopped")

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    # ═══════════════════════════════════════════════════════════
    #  MAIN SCAN LOOP
    # ═══════════════════════════════════════════════════════════

    async def run_loop(self):
        """
        Main async loop — actively scans market every 15 seconds for short-term scalping opportunities.
        """
        scan_count = 0
        last_scan_time = 0.0

        # Immediate first scan on bot start so trader doesn't have to wait
        logger.info("🚀 Running initial scalping scan on startup...")
        try:
            for symbol in ACTIVE_PAIRS:
                await self._scan_symbol(symbol)
            scan_count += 1
        except Exception as e:
            logger.debug(f"Initial scan error: {e}")

        while self._running:
            try:
                now = time.time()

                # 1. Heartbeat every 10s
                if int(now) % 10 == 0:
                    await message_bus.publish_heartbeat(
                        self.PROCESS_NAME, "HEALTHY", self.uptime
                    )

                # 2. Check if market is open
                if not self._market_data or not self._market_data.is_market_open():
                    await asyncio.sleep(2.0)
                    continue

                # 3. Fast Scalping Scan every 15 seconds
                if now - last_scan_time >= 15.0:
                    last_scan_time = now
                    scan_count += 1

                    # Ensure market data service pulls latest OHLC
                    if hasattr(self._market_data, "_poll_ohlc"):
                        try:
                            await self._market_data._poll_ohlc()
                        except Exception as e:
                            logger.debug(f"OHLC refresh error: {e}")

                    for symbol in ACTIVE_PAIRS:
                        await self._scan_symbol(symbol)

                await asyncio.sleep(1.0)

            except Exception as e:
                logger.error(f"StrategyEngine loop error: {e}", exc_info=True)
                await asyncio.sleep(3.0)

    # ═══════════════════════════════════════════════════════════
    #  SYMBOL SCANNING
    # ═══════════════════════════════════════════════════════════

    async def _scan_symbol(self, symbol: str):
        """Run all strategies against a symbol and publish any signals."""
        # Get cached data from market data service
        multi_tf = self._market_data.get_cached_multi_tf(symbol)
        df_h4 = multi_tf.get(TF_H4)
        df_h1 = multi_tf.get(TF_H1)
        df_m15 = multi_tf.get(TF_M15)
        df_m5 = multi_tf.get(TF_M5)

        # Differentiate Timeframe: Gold Big Trades (M15/H1) vs Forex Scalping (M5/M15)
        is_gold = "XAU" in symbol.upper() or symbol in ("XAUUSD", "GOLD")
        if is_gold:
            # Big Trades for Gold: evaluate closed M15 bars with H1 structure / H4 context
            df_entry = df_m15.iloc[:-1] if df_m15 is not None and len(df_m15) > 25 else (df_h1.iloc[:-1] if df_h1 is not None and len(df_h1) > 25 else df_m15)
            df_htf = df_h1.iloc[:-1] if df_h1 is not None and len(df_h1) > 20 else df_h4
            eval_tf = "M15"
        else:
            # Scalping for Forex: evaluate closed M5 bars with M15 structure
            if df_m5 is not None and len(df_m5) >= 25:
                df_entry = df_m5.iloc[:-1] if len(df_m5) > 25 else df_m5
                df_htf_raw = df_m15 if df_m15 is not None and len(df_m15) >= 20 else (df_h1 if df_h1 is not None and len(df_h1) >= 20 else df_h4)
                df_htf = df_htf_raw.iloc[:-1] if df_htf_raw is not None and len(df_htf_raw) > 20 else df_htf_raw
            else:
                df_entry = df_m15.iloc[:-1] if len(df_m15) > 25 else df_m15
                df_htf = df_h1.iloc[:-1] if df_h1 is not None and len(df_h1) >= 20 else df_h4
            eval_tf = "M5"

        if df_entry is None or len(df_entry) < 25:
            return

        # Detect market regime using institutional 9-state engine
        from zohra.core.market_regime import market_regime_engine
        spread_pips = self._market_data.get_spread_pips(symbol) if self._market_data else 2.0
        regime_report = market_regime_engine.classify_regime(df_entry, df_htf, current_spread_pips=spread_pips)
        regime = regime_report.regime

        # Check if regime is tradable
        if not self._profile.is_regime_tradable(regime.value if hasattr(regime, 'value') else str(regime)):
            return

        # Collect all candidate signals across enabled strategies
        candidates = []
        for strategy_name, strategy_instance in self._strategies.items():
            try:
                signal = self._run_strategy(
                    strategy_name, strategy_instance,
                    symbol, regime_report,
                    df_entry=df_entry, df_htf=df_htf, spread_pips=spread_pips,
                    timeframe=eval_tf
                )
                if signal and signal.get("direction"):
                    candidates.append(signal)
            except Exception as e:
                logger.debug(f"Strategy {strategy_name} error on {symbol}: {e}")

        if not candidates:
            return

        # ─── PARTITION CANDIDATES BY ACCOUNT (5 STRATEGIES PER ACCOUNT) ───
        from collections import defaultdict
        from zohra.config.bot_profile import get_account_for_strategy, get_profile_for_account

        acct_candidates = defaultdict(list)
        for cand in candidates:
            strat_name = cand.get("strategy", "")
            acct_id = get_account_for_strategy(strat_name)
            if acct_id:
                acct_candidates[acct_id].append(cand)

        if not acct_candidates:
            return

        # 3. Evaluate setups for each account independently (strict 5-strategy adherence)
        account_best_signals = {}
        for acct_id, a_candidates in acct_candidates.items():
            profile = get_profile_for_account(acct_id)
            min_conf = getattr(profile, "min_confirmations", 1)

            buy_signals = [s for s in a_candidates if s["direction"] == "BUY"]
            sell_signals = [s for s in a_candidates if s["direction"] == "SELL"]

            # Internal account consensus within its own 5 strategies
            if buy_signals and sell_signals:
                buy_conf = sum(s.get("confidence", 70) for s in buy_signals)
                sell_conf = sum(s.get("confidence", 70) for s in sell_signals)
                winning_signals = buy_signals if buy_conf > sell_conf else sell_signals
                winning_dir = "BUY" if buy_conf > sell_conf else "SELL"
            elif buy_signals:
                winning_signals = buy_signals
                winning_dir = "BUY"
            elif sell_signals:
                winning_signals = sell_signals
                winning_dir = "SELL"
            else:
                continue

            if len(winning_signals) < min_conf:
                continue

            winning_signals.sort(
                key=lambda x: (x.get("confidence", 0), x.get("setup_quality", 0)),
                reverse=True
            )
            best_sig = winning_signals[0]
            supporting_strats = [s["strategy"] for s in winning_signals[1:]]
            base_conf = float(best_sig.get("confidence", 70.0))
            boosted_conf = min(98.0, base_conf + (len(winning_signals) - 1) * 5.0)

            account_best_signals[acct_id] = {
                "signal": best_sig,
                "direction": winning_dir,
                "confidence": boosted_conf,
                "confirmations": len(winning_signals),
                "supporting": supporting_strats,
            }

        if not account_best_signals:
            return

        # 4. Cross-Bot Conflict Arbitration (prevent simultaneous opposing signals on same symbol)
        directions = {acct_id: data["direction"] for acct_id, data in account_best_signals.items()}
        unique_dirs = set(directions.values())
        if len(unique_dirs) > 1:
            # Multi-account opposing conflict in same scan window: pick dominant side via confidence & regime
            buy_accts = [aid for aid, d in directions.items() if d == "BUY"]
            sell_accts = [aid for aid, d in directions.items() if d == "SELL"]
            total_buy_conf = sum(account_best_signals[aid]["confidence"] for aid in buy_accts)
            total_sell_conf = sum(account_best_signals[aid]["confidence"] for aid in sell_accts)

            regime_str = (regime.value if hasattr(regime, 'value') else str(regime)).lower()
            if "up" in regime_str or "bull" in regime_str:
                total_buy_conf += 20
            elif "down" in regime_str or "bear" in regime_str:
                total_sell_conf += 20

            dominant_dir = "BUY" if total_buy_conf >= total_sell_conf else "SELL"
            deferred_accts = sell_accts if dominant_dir == "BUY" else buy_accts
            for da in deferred_accts:
                logger.info(
                    f"⚖️ [CROSS-BOT ARBITRATION] {da} ({directions[da]}) deferred on {symbol} -> "
                    f"dominant {dominant_dir} selected to strictly prevent simultaneous opposing trades across accounts."
                )
                account_best_signals.pop(da, None)

        # 5. Publish signals dedicated to their respective target account
        trade_mode = "BIG TRADE" if is_gold else "SCALP"
        for acct_id, data in account_best_signals.items():
            best_signal = data["signal"]
            winning_dir = data["direction"]
            boosted_confidence = data["confidence"]
            confirmations = data["confirmations"]
            supporting_strategies = data["supporting"]

            signal_id = str(uuid.uuid4())
            self._signal_count += 1

            await message_bus.publish_strategy_signal(
                signal_id=signal_id,
                strategy_id=best_signal["strategy"],
                symbol=symbol,
                timeframe=best_signal.get("timeframe", eval_tf),
                direction=winning_dir,
                entry=best_signal.get("entry", 0.0),
                stop_loss=best_signal.get("stop_loss", 0.0),
                take_profit=best_signal.get("take_profit", 0.0),
                confidence=boosted_confidence,
                target_account=acct_id,
                source=self.PROCESS_NAME,
            )

            logger.info(
                f"📡 DEDICATED {trade_mode} SIGNAL [{best_signal['strategy']}] {winning_dir} {symbol} ({best_signal.get('timeframe', eval_tf)}) "
                f"→ {acct_id} | @ {best_signal.get('entry', 'market')} | "
                f"SL={best_signal.get('stop_loss')} TP={best_signal.get('take_profit')} | "
                f"Confidence={boosted_confidence:.0f}% | "
                f"Confirmations={confirmations} (supporting: {', '.join(supporting_strategies) if supporting_strategies else 'none'})"
            )

    def _run_strategy(self, name: str, instance: Any, symbol: str, regime_report,
                      df_entry=None, df_htf=None, spread_pips: float = 2.0,
                      timeframe: str = "M5") -> Optional[Dict]:
        """
        Run a single strategy and return normalized signal dict or None.
        - Gold (XAUUSD): Big structural trade with wide ATR stop ($12-$18) and large swing target ($25-$45+).
        - Forex Pairs: Fast scalping with tight risk ($1.50-$2.20) and quick profit banking ($2.20-$3.50).
        """
        # Primary interface: BaseStrategy.evaluate(df_entry, df_htf, regime_report, current_spread_pips)
        if hasattr(instance, 'evaluate'):
            try:
                cand = instance.evaluate(
                    df_entry=df_entry,
                    df_htf=df_htf,
                    regime_report=regime_report,
                    current_spread_pips=spread_pips
                )
                if cand and getattr(cand, 'is_valid', False):
                    last_close = float(df_entry["close"].iloc[-1]) if df_entry is not None and len(df_entry) > 0 else float(cand.entry_price)
                    decimals = 5 if last_close < 10 else (3 if last_close < 500 else 2)
                    entry_p = round(float(cand.entry_price), decimals)

                    # FIX: Safely extract direction from candidate
                    dir_str = str(cand.direction).upper().strip()

                    # Calibrate SL and TP dynamically: Big Trades for Gold vs Scalps for Forex
                    sl_p, tp_p = self._calibrate_trade_levels(symbol, dir_str, entry_p, df_entry)

                    # Strict geometry sanity check:
                    if dir_str == "BUY" and not (sl_p < entry_p < tp_p):
                        logger.warning(f"⚠️ Invalid BUY geometry from {name} on {symbol}: SL={sl_p}, Entry={entry_p}, TP={tp_p}")
                        return None
                    elif dir_str == "SELL" and not (sl_p > entry_p > tp_p):
                        logger.warning(f"⚠️ Invalid SELL geometry from {name} on {symbol}: SL={sl_p}, Entry={entry_p}, TP={tp_p}")
                        return None

                    return {
                        "strategy": name,
                        "symbol": symbol,
                        "direction": dir_str,
                        "entry": entry_p,
                        "stop_loss": sl_p,
                        "take_profit": tp_p,
                        "confidence": float(getattr(cand, 'confidence', 70.0)),
                        "timeframe": timeframe,
                        "setup_quality": getattr(cand, 'setup_quality', 80),
                    }
            except Exception as e:
                logger.debug(f"Strategy {name} evaluate error on {symbol}: {e}")

        # Fallback legacy interfaces (generate_signal, analyze, scan)
        if hasattr(instance, 'generate_signal'):
            try:
                sig_func = instance.generate_signal
                import inspect
                params = inspect.signature(sig_func).parameters
                res = None
                if len(params) >= 4:
                    res = sig_func(symbol, df_entry, df_htf, None)
                elif len(params) >= 2:
                    res = sig_func(df_entry, symbol)
                if isinstance(res, dict) and res.get('direction'):
                    return res
            except Exception as e:
                logger.debug(f"Legacy generate_signal error for {name}: {e}")

        return None

    @staticmethod
    def _calibrate_trade_levels(symbol: str, direction: str, entry_price: float, df_entry=None) -> tuple:
        """
        Calibrates SL and TP:
        - XAUUSD (Gold): Big structural trade with wide ATR stop ($12-$18) and large profit target ($25-$45+).
        - JPY Pairs (USDJPY, GBPJPY): Fast scalping (~25 pips TP, ~16 pips SL).
        - Standard Forex (EURUSD, GBPUSD): Fast scalping (~11 pips TP, ~7.5 pips SL).
        """
        clean_sym = symbol.upper()
        dir_clean = str(direction).upper().strip()
        is_buy = dir_clean in ("BUY", "LONG")

        if "XAU" in clean_sym or "GOLD" in clean_sym:
            # ─── BIG TRADES (XAUUSD / Gold) ───
            # Dynamic ATR calculation for healthy breathing room outside noise
            atr_val = 8.0
            if df_entry is not None and len(df_entry) >= 14:
                try:
                    from zohra.indicators.atr import calculate_atr
                    calc_atr = calculate_atr(df_entry, period=14)
                    if calc_atr and float(calc_atr) > 1.0:
                        atr_val = float(calc_atr)
                except Exception:
                    pass
            # 0.01 lot on Gold: 1.0 point = $1.00
            # Safe structural stop: at least $12.00, scaled by 1.5x ATR (e.g. $12.00 - $18.00)
            sl_dist = max(12.0, round(1.5 * atr_val, 2))
            # Big Swing TP: at least $25.00, aiming for 2.2x to 2.5x SL (e.g. $26.00 - $45.00)
            tp_dist = max(25.0, round(2.2 * sl_dist, 2))
            decimals = 2
        elif "JPY" in clean_sym:
            # ─── JPY SCALP (USDJPY, GBPJPY) ───
            # 0.02 lot: 1 pip = ~$0.14
            tp_dist = 0.25   # ~25 pips -> ~$3.50 profit
            sl_dist = 0.16   # ~16 pips -> ~$2.20 risk
            decimals = 3
        else:
            # ─── STANDARD FOREX SCALP (EURUSD, GBPUSD) ───
            # 0.02 lot: 1 pip = $0.20
            # 11 pips = $2.20 target profit, 7.5 pips = $1.50 risk (1:1.47 R:R)
            tp_dist = 0.00110  # 11 pips -> $2.20 target profit
            sl_dist = 0.00075  # 7.5 pips -> $1.50 risk
            decimals = 5

        if is_buy:
            tp = round(entry_price + tp_dist, decimals)
            sl = round(entry_price - sl_dist, decimals)
        else:
            tp = round(entry_price - tp_dist, decimals)
            sl = round(entry_price + sl_dist, decimals)

        return sl, tp

    # Backward-compatible alias
    _calibrate_scalp_levels = _calibrate_trade_levels

    # ═══════════════════════════════════════════════════════════
    #  STATS
    # ═══════════════════════════════════════════════════════════

    def get_stats(self) -> Dict[str, Any]:
        return {
            "process": self.PROCESS_NAME,
            "loaded_strategies": list(self._strategies.keys()),
            "strategy_count": len(self._strategies),
            "signals_generated": self._signal_count,
            "uptime_seconds": self.uptime,
        }
