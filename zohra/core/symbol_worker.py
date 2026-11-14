import asyncio
import logging
import datetime as dt
from typing import Dict, List, Optional
from zohra.config.settings import settings, HYBRID_SCALPER_MODE, TRADING_DIAGNOSTIC_MODE, BOT_NAME
from zohra.brokers.mt5_broker import mt5_broker
from zohra.core.market_regime import regime_detector
from zohra.core.adaptive_scorer import adaptive_scorer
from zohra.core.enums import MarketRegime, StrategyName
from zohra.core.symbol_manager import symbol_manager
from zohra.core.scout_engine import scout_engine
from zohra.core.symbol_resolver import symbol_resolver

logger = logging.getLogger("zohra.symbol_worker")

class SymbolWorker:
    """
    Independent asynchronous worker task for a single trading symbol (Gold / Silver).
    Fetches data using thread pools and runs stateless analysis pipelines.
    """
    def __init__(self, symbol: str, brain):
        self.symbol = symbol
        self.brain = brain
        self.running = False
        self.last_bar_time = 0.0
        self.task: Optional[asyncio.Task] = None

    def get_priority_settings(self):
        """Returns (check_timeframe, bar_size_seconds, scan_sleep_seconds)."""
        return "M5", 300, 10

    def start(self):
        self.running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info(f"👷 Worker started for {self.symbol}")

    def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            logger.info(f"🛑 Worker stopped for {self.symbol}")

    async def _run_loop(self):
        import random
        await asyncio.sleep(random.uniform(0.1, 1.5))

        while self.running:
            try:
                # 0. Hard Symbol Guard
                if not symbol_resolver.guard(self.symbol, "SymbolWorker"):
                    logger.warning(f"🛑 SymbolWorker stopping for non-permitted symbol {self.symbol}")
                    break

                # 1. Market Open Validation
                if not symbol_manager.is_market_open(self.symbol):
                    if TRADING_DIAGNOSTIC_MODE:
                        logger.debug(f"[DIAGNOSTIC] Market closed for {self.symbol}. Sleeping 15s...")
                    await asyncio.sleep(15)
                    continue

                # 2. Check health status from manager
                if not symbol_manager.is_active(self.symbol):
                    await asyncio.sleep(15)
                    continue

                # 3. Fetch recent M5 candles to check bar status
                df_check = await asyncio.to_thread(mt5_broker.get_ohlcv, self.symbol, "M5", 2)
                if df_check is None or df_check.empty:
                    await asyncio.sleep(5)
                    continue

                latest_m5_time = df_check.index[-1].timestamp()

                # If candle was already processed and not first run, sleep short interval
                if self.last_bar_time != 0.0 and self.last_bar_time == latest_m5_time:
                    import time
                    now = time.time()
                    sec_left = 300 - (now % 300)
                    sleep_dur = max(5.0, min(sec_left + 1.0, 15.0))
                    await asyncio.sleep(sleep_dur)
                    continue

                # 4. A new bar has closed or first startup scan! Fetch full multi-timeframe data
                dfs = await asyncio.to_thread(
                    mt5_broker.get_multi_tf,
                    self.symbol,
                    ["D1", "H4", "H1", "M15", "M5"],
                    300
                )
                df_m5 = dfs.get("M5")
                df_m15 = dfs.get("M15")
                
                if df_m5 is None or df_m15 is None or len(df_m15) < 50:
                    await asyncio.sleep(5)
                    continue

                self.last_bar_time = latest_m5_time

                if TRADING_DIAGNOSTIC_MODE:
                    logger.info(f"━━━━━━━━ SCAN STARTED: {self.symbol} ━━━━━━━━")
                    logger.info(f"[DIAGNOSTIC] Account: {BOT_NAME} | Symbol: {self.symbol} | M5 Bars: {len(df_m5)} | M15 Bars: {len(df_m15)}")

                # 5. News check via news agent
                news_status = self.brain.news_agent.check_news_status(self.symbol)
                is_news_blackout = (news_status.get("status") == "BLACKOUT")

                # 6. Execute Unified 5-Strategy Regime Evaluation
                from zohra.strategies.regime_suite import regime_strategy_suite
                from zohra.core.market_regime import regime_engine

                regime_info = regime_engine.classify(df_m15)
                regime = regime_info["regime"]

                tick = await asyncio.to_thread(mt5_broker.get_tick, self.symbol) if hasattr(mt5_broker, "get_tick") else {}
                ask = tick.get("ask", 0.0) if isinstance(tick, dict) else getattr(tick, "ask", 0.0)
                bid = tick.get("bid", 0.0) if isinstance(tick, dict) else getattr(tick, "bid", 0.0)

                winning_sig, diag_box = await asyncio.to_thread(
                    regime_strategy_suite.evaluate,
                    df_m5, self.symbol, ask, bid, {"M15": df_m15}
                )

                # Always log the structured evaluation box
                print("\n" + diag_box + "\n")
                logger.info(f"📊 {self.symbol} Cycle Evaluation: Regime={regime.value.upper()} | Decision={'TRADE' if winning_sig else 'NO_TRADE'}")

                proposals = [winning_sig] if winning_sig else []

                # 8. Score and Register Setup to central Opportunity Engine & Scout
                for prop in proposals:
                    direction = prop["direction"]
                    strategy_used = prop["strategy"]
                    
                    df_to_score = df_m5 if strategy_used in (StrategyName.SCALP_M5.value, "Scalping", StrategyName.MEAN_REVERSION.value) else df_m15
                    confl = await asyncio.to_thread(
                        adaptive_scorer.evaluate_confluence,
                        df_to_score, direction, self.symbol, regime, strategy_used
                    )
                    
                    final_score = confl["final_score"]

                    # Calculate volume ratio on M5
                    try:
                        vol_col = 'tick_volume'
                        if 'real_volume' in df_m5.columns and df_m5['real_volume'].sum() > 0:
                            vol_col = 'real_volume'
                        latest_vol = df_m5[vol_col].iloc[-1]
                        vol_sma = df_m5[vol_col].rolling(20).mean().iloc[-1]
                        vol_ratio = float(latest_vol / (vol_sma + 1e-9))
                    except Exception:
                        vol_ratio = 1.0

                    setup = {
                        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "symbol": self.symbol,
                        "direction": direction,
                        "strategy": strategy_used,
                        "regime": regime.value,
                        "confidence_score": final_score,
                        "news_status": "BLACKOUT" if is_news_blackout else "CLEAR",
                        "entry_price": prop.get("entry_price") or prop.get("entry"),
                        "stop_loss": prop.get("stop_loss") or prop.get("stop"),
                        "take_profit": prop.get("take_profit") or prop.get("tp2") or prop.get("tp1"),
                        "scores_breakdown": confl["scores"],
                        "weights_used": confl["weights"],
                        "reasons": confl["reasons"],
                        "is_news_blackout": is_news_blackout,
                        "news_reason": news_status.get("reason", ""),
                        "vol_ratio": vol_ratio
                    }

                    if TRADING_DIAGNOSTIC_MODE:
                        logger.info(f"[DIAGNOSTIC] Setup Generated: {self.symbol} {direction} ({strategy_used}) | Confidence Score: {final_score}/100")

                    # Register candidate setup to the brain's opportunity leaderboard
                    self.brain.opportunity_engine.register_setup(setup)

                    # Also execute Layer 1 Scout probe if HYBRID_SCALPER_MODE is active
                    if HYBRID_SCALPER_MODE:
                        logger.info(f"🏹 [Hybrid Mode] Directing setup on {self.symbol} to Scout Engine...")
                        await scout_engine.evaluate_and_execute_probe(self.symbol, setup)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker loop for {self.symbol}: {e}")
                await asyncio.sleep(15)

            await asyncio.sleep(settings.SCAN_INTERVAL_SEC)
