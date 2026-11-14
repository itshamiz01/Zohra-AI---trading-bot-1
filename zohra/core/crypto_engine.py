"""
╔══════════════════════════════════════════════════════════════════════╗
║                   ZOHRA — CRYPTO MARKET ENGINE                       ║
║            24/7 Multi-Asset Cryptocurrency Subsystem                 ║
║                                                                      ║
║  This module manages autonomous crypto trading loops, integrating   ║
║  portfolio management, risk verification, and execution.            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import logging
import time
import uuid
import datetime as dt
from typing import Dict, List, Any, Optional

from zohra.config.settings import STATE, settings
from zohra.brokers.manager import broker_manager
from zohra.core.symbol_manager import symbol_manager
from zohra.core.risk_guardian import risk_guardian
from zohra.core.crypto_risk import crypto_risk_guardian
from zohra.core.crypto_portfolio import crypto_portfolio_manager
from zohra.core.crypto_intelligence import crypto_intelligence
from zohra.strategies.crypto_strategies import crypto_momentum_strategy, crypto_smc_strategy
from zohra.event_bus import event_bus
from zohra.db.schema import db
from zohra.security.permissions import trading_permission_gateway

logger = logging.getLogger("zohra.crypto_engine")

class CryptoMarketEngine:
    """
    Main orchestrator for cryptocurrency assets trading.
    Runs 24/7/365 as a background daemon inside ZOHRA AI OS.
    """

    def __init__(self):
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.task: Optional[asyncio.Task] = None
        
        # Crypto-specific active trading registry
        self.crypto_pairs = ["BTCUSDT", "ETHUSDT"]
        self.strategies = {
            "Crypto_Momentum": crypto_momentum_strategy,
            "Crypto_SMC": crypto_smc_strategy
        }

    def start(self, parent_loop = None):
        """Starts the crypto engine loop in the background."""
        self.running = True
        self.loop = parent_loop or asyncio.get_event_loop()
        self.task = self.loop.create_task(self._run_loop())
        logger.info("🪙 ZOHRA Crypto Market Engine initialized successfully.")

    def stop(self):
        """Stops the crypto engine loop."""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.warning("🛑 ZOHRA Crypto Market Engine stopped.")

    async def _run_loop(self):
        """24/7 background execution check."""
        # Stagger startup to allow MAL connections
        await asyncio.sleep(5)

        logger.info("🪙 ZOHRA Crypto Market Engine loop active.")
        
        while self.running:
            try:
                # 1. Connection check
                if not broker_manager.is_connected(broker="coindcx"):
                    logger.warning("🔌 CoinDCX adapter disconnected! Reconnecting...")
                    await asyncio.to_thread(broker_manager.reconnect, "coindcx")
                    await asyncio.sleep(15)
                    continue

                # 2. Portfolio compilation & auto-rebalancing checks
                try:
                    portfolio = crypto_portfolio_manager.get_portfolio_status()
                    # Rebalancing produces recommendations only. Financial
                    # execution must enter through the normal permission gate.
                    if portfolio.get("status") == "success" and portfolio.get("rebalance_needed"):
                        logger.info(
                            "Crypto portfolio rebalance recommended; no order is submitted automatically: %s",
                            crypto_portfolio_manager.evaluate_rebalance_trades(),
                        )
                except Exception as pe:
                    logger.error(f"Error checking crypto portfolio rebalance: {pe}")

                # 3. Dynamic scanner checks
                for symbol in self.crypto_pairs:
                    try:
                        # Fetch candles (M5/M15/H1)
                        df_m5 = await asyncio.to_thread(broker_manager.get_ohlcv, symbol, "M5", 100, broker="coindcx")
                        df_m15 = await asyncio.to_thread(broker_manager.get_ohlcv, symbol, "M15", 100, broker="coindcx")
                        
                        if df_m5 is None or df_m5.empty or df_m15 is None or df_m15.empty:
                            continue

                        # Evaluate strategies
                        for name, strat in self.strategies.items():
                            signal = strat.generate_signal(df_m15, symbol)
                            if signal:
                                # Process the candidate signal through the institutional pipeline
                                await self._process_signal_pipeline(signal)
                    except Exception as se:
                        logger.error(f"Error scanning {symbol} via crypto engine: {se}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in CryptoMarketEngine loop: {e}")
                
            # Scan interval (every 30 seconds)
            await asyncio.sleep(30)

    async def _process_signal_pipeline(self, signal: Dict[str, Any]):
        """
        AI Decision Pipeline:
        Scanner -> Strategy -> AI Analysis -> Confidence -> Risk -> Capital Allocation -> Execution -> Journal -> Learning
        """
        symbol = signal["symbol"]
        direction = signal["direction"]
        strategy = signal["strategy"]
        entry = signal["entry_price"]
        sl = signal["stop_loss"]
        tp = signal["take_profit"]
        
        logger.info(f"🔍 [Crypto Pipeline] Setup found: {direction} {symbol} ({strategy}) at {entry}")

        # 1. Strategy confidence is derived from signal metadata; it is not
        # manufactured when an upstream strategy omitted the measurement.
        confidence = signal.get("confidence")
        indicators = signal.get("indicators", {})
        if isinstance(confidence, (int, float)) and "rsi" in indicators:
            rsi_val = indicators["rsi"]
            if direction == "LONG" and rsi_val > 55: confidence += 5
            if direction == "SHORT" and rsi_val < 45: confidence += 5

        if not STATE.trading_enabled or STATE.trading_halted:
            logger.info("Crypto signal ignored because trading is paused or halted.")
            return

        # 2. Risk Validation (Evaluate safety checks: drawdown, spreads, volatility, exposure limits)
        lots = 0.01  # test size
        is_safe, risk_reason = risk_guardian.evaluate_execution_safety(
            symbol, direction, lots, is_probe=False
        )
        if not is_safe:
            logger.warning(f"⏭️  [Crypto Pipeline] Risk Guardian vetoed setup on {symbol}: {risk_reason}")
            # Log setup rejection to DB
            await event_bus.publish("db_log_rejection", {
                "symbol": symbol,
                "direction": direction,
                "strategy": strategy,
                "reason": risk_reason,
                "confidence_score": confidence
            })
            return

        permission = trading_permission_gateway.authorize_trade_execution({
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "broker": "coindcx",
            "risk_approved": True,
            "consensus_status": "APPROVED",
        })
        if not permission.approved:
            logger.warning("Crypto execution vetoed: %s", permission.reason)
            await event_bus.publish("db_log_rejection", {
                "symbol": symbol,
                "direction": direction,
                "strategy": strategy,
                "reason": permission.reason,
                "confidence_score": confidence,
            })
            return

        # 3. Capital Sizing & Allocation
        try:
            equity = broker_manager.get_equity(broker="coindcx")
            if equity <= 0:
                equity = 10000.0  # fallback
            # Target 0.5% risk per trade
            risk_usd = equity * 0.005
            lots = crypto_risk_guardian.calculate_lot_size(symbol, equity, sl, entry, risk_usd)
        except Exception as ce:
            logger.error(f"Error calculating lot size for crypto setup: {ce}")
            lots = 0.01

        # 4. Order Execution
        order = {
            "symbol": symbol,
            "direction": direction,
            "volume_lots": lots,
            "stop_loss": sl,
            "take_profit": tp,
            "comment": f"ZCR_{strategy[:5]}",
            "magic": 88888
        }

        logger.info(f"🏹 [Crypto Pipeline] Placing order: {direction} {symbol} ({lots} lots) on CoinDCX...")
        
        t_start = time.perf_counter()
        exec_res = await asyncio.to_thread(broker_manager.open_position, order, broker="coindcx")
        latency = (time.perf_counter() - t_start) * 1000.0

        if exec_res.get("success"):
            ticket = exec_res.get("mt5_ticket") or int(time.time() * 1000)
            fill_price = exec_res.get("fill_price", entry)
            logger.info(f"🎯 [Crypto Pipeline] Position filled! Ticket #{ticket} at {fill_price} | Latency={latency:.1f}ms")

            # 5. Trade Journal (Insert to SQL DB & Vector Memory)
            trade_id = f"ZHR_CRYP_{symbol}_{uuid.uuid4().hex[:8].upper()}"
            trade_record = {
                "trade_id": trade_id,
                "timestamp_open": dt.datetime.utcnow().isoformat(),
                "symbol": symbol,
                "direction": direction,
                "entry_price": fill_price,
                "stop_loss": sl,
                "take_profit": tp,
                "confidence_score": confidence,
                "session": "24h",
                "market_regime": "crypto_trending",
                "strategy": strategy,
                "news_status": "CLEAR",
                "reason_for_entry": signal.get("reason", "Crypto momentum shift"),
                "risk_reward_ratio": round(abs(tp - entry) / (abs(entry - sl) + 1e-9), 2),
                "mt5_ticket": ticket,
                "broker": "coindcx",
                "asset_class": "crypto",
                "position_size_lots": lots,
                "risk_usd": round(risk_usd, 2),
                "requested_price": entry,
                "slippage_points": 0.0,
                "entry_spread_points": 0.0,
                "execution_latency_ms": latency,
                "metadata": {"indicators": indicators}
            }
            
            # Save trade open events
            await event_bus.publish("db_log_trade_open", trade_record)
            await event_bus.publish("memory_log_trade_open", trade_record)
            
            logger.info(f"💾 [Crypto Pipeline] Trade successfully journaled to DB and AI memory system.")
        else:
            logger.error(f"❌ [Crypto Pipeline] Order execution failed: {exec_res.get('comment')}")

crypto_engine = CryptoMarketEngine()
