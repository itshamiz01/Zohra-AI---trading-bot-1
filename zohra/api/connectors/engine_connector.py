import logging
from typing import Dict, List, Any, Optional
import zohra.config.settings as settings
from zohra.brokers.mt5_broker import mt5_broker
from zohra.core.signal_scorer import scorer
from zohra.core.market_regime import regime_detector

logger = logging.getLogger("zohra.api.connectors.engine")

class EngineConnector:
    """
    Control connector for interacting with the MetaTrader 5 terminal,
    fetching live account states, modifying risk variables, and querying
    real-time market regimes.
    """

    def get_account_summary(self) -> Dict[str, Any]:
        """Fetch real-time equity, balance, margins, and active trade counts from MT5."""
        try:
            info = mt5_broker.get_account_info()
            if not info:
                # Provide a simulated fallback if MT5 is not connected or in dry run
                return {
                    "connected": False,
                    "login": 0,
                    "server": "Not Connected",
                    "equity": 10000.0,
                    "balance": 10000.0,
                    "margin": 0.0,
                    "free_margin": 10000.0,
                    "profit": 0.0,
                    "drawdown_pct": 0.0,
                    "open_positions_count": 0
                }
            
            open_positions = mt5_broker.get_open_positions()
            count = len(open_positions)
            
            # Drawdown calculation
            equity = info.get("equity", 0.0)
            balance = info.get("balance", 0.0)
            drawdown = 0.0
            if balance > 0:
                drawdown = ((balance - equity) / balance) * 100.0 if equity < balance else 0.0
                
            return {
                "connected": True,
                "login": info.get("login"),
                "server": info.get("server"),
                "equity": round(equity, 2),
                "balance": round(balance, 2),
                "margin": round(info.get("margin", 0.0), 2),
                "free_margin": round(info.get("free_margin", 0.0), 2),
                "profit": round(info.get("profit", 0.0), 2),
                "drawdown_pct": round(drawdown, 2),
                "open_positions_count": count
            }
        except Exception as e:
            logger.error(f"Error getting account summary: {e}")
            return {"error": str(e)}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Fetch active trade details from MetaTrader 5."""
        try:
            return mt5_broker.get_open_positions()
        except Exception as e:
            logger.error(f"Error getting open positions: {e}")
            return []

    def get_risk_parameters(self) -> Dict[str, Any]:
        """Fetch current risk and scoring thresholds."""
        try:
            return {
                "risk_per_trade_pct": round(settings.RISK_PER_TRADE_PCT * 100.0, 2),
                "max_open_positions": settings.MAX_OPEN_POSITIONS,
                "max_daily_loss_pct": round(settings.MAX_DAILY_LOSS_PCT * 100.0, 2),
                "min_smc_score_swing": settings.MIN_SMC_SCORE_SWING,
                "trading_enabled": settings.STATE.trading_enabled,
                "trading_halted": settings.STATE.trading_halted,
                "halt_reason": settings.STATE.halt_reason
            }
        except Exception as e:
            logger.error(f"Error getting risk parameters: {e}")
            return {}

    def modify_risk(self, risk_pct: float) -> bool:
        """Dynamically adjust risk percentage per trade in both config and scorer."""
        try:
            val_decimal = risk_pct / 100.0
            settings.RISK_PER_TRADE_PCT = val_decimal
            scorer.risk_per_trade = val_decimal
            logger.info(f"🔄 Risk size updated via Chat: {risk_pct}% per trade")
            return True
        except Exception as e:
            logger.error(f"Error modifying risk to {risk_pct}%: {e}")
            return False

    def halt_trading(self, reason: str = "Chat request") -> bool:
        """Pause trading sweeps and engine execution."""
        try:
            settings.STATE.trading_enabled = False
            settings.STATE.trading_halted = True
            settings.STATE.halt_reason = reason
            logger.warning(f"🛑 Trading HALTED via Chat: {reason}")
            return True
        except Exception as e:
            logger.error(f"Error halting trading: {e}")
            return False

    def resume_trading(self) -> bool:
        """Resume active trading sweeps and engine execution."""
        try:
            settings.STATE.trading_enabled = True
            settings.STATE.trading_halted = False
            settings.STATE.halt_reason = ""
            logger.info("✅ Trading RESUMED via Chat")
            return True
        except Exception as e:
            logger.error(f"Error resuming trading: {e}")
            return False

    def close_all_positions(self) -> int:
        """Emergency exit all positions."""
        try:
            closed_count = mt5_broker.close_all_positions(comment="Chat-Emergency-Close")
            logger.warning(f"🚨 Emergency closed all positions: {closed_count} positions exit.")
            return closed_count
        except Exception as e:
            logger.error(f"Error emergency closing all positions: {e}")
            return 0

    def close_profitable_positions(self) -> int:
        """Close only open positions that are currently in profit."""
        try:
            positions = mt5_broker.get_open_positions()
            closed_count = 0
            for pos in positions:
                if pos.get("profit", 0.0) > 0.0:
                    res = mt5_broker.close_trade(
                        ticket=pos["ticket"],
                        symbol=pos["symbol"],
                        direction=pos["direction"],
                        comment="Chat-Close-Profit"
                    )
                    if res and res.get("success"):
                        closed_count += 1
            logger.info(f"💰 Closed {closed_count} profitable positions.")
            return closed_count
        except Exception as e:
            logger.error(f"Error closing profitable positions: {e}")
            return 0

    def get_market_analysis(self, symbol: str) -> Dict[str, Any]:
        """Perform immediate indicator regime checks for a symbol using H1 timeframe."""
        try:
            # Check connection
            connected = mt5_broker.is_connected()
            if not connected:
                # Try to connect
                mt5_broker.connect()
                
            df = mt5_broker.get_ohlcv(symbol.upper(), "H1", count=100)
            if df is None or df.empty:
                return {
                    "symbol": symbol.upper(),
                    "error": "Could not retrieve market data from MT5.",
                    "regime": "UNKNOWN"
                }
                
            details = regime_detector.detect_with_details(df)
            # Map enum to string name
            if hasattr(details.get("regime"), "name"):
                details["regime"] = details["regime"].name
                
            # Add latest price
            details["symbol"] = symbol.upper()
            details["latest_price"] = round(float(df.iloc[-1]['close']), 5)
            
            # Simple Trend Direction
            ema20 = details.get("ema20") if "ema20" in details else float(df['close'].ewm(span=20, adjust=False).mean().iloc[-1])
            ema50 = details.get("ema50") if "ema50" in details else float(df['close'].ewm(span=50, adjust=False).mean().iloc[-1])
            if details["latest_price"] > ema20 > ema50:
                details["trend_direction"] = "BULLISH"
            elif details["latest_price"] < ema20 < ema50:
                details["trend_direction"] = "BEARISH"
            else:
                details["trend_direction"] = "NEUTRAL / SIDEWAYS"
                
            return details
        except Exception as e:
            logger.error(f"Error performing market analysis for {symbol}: {e}")
            return {"symbol": symbol.upper(), "error": str(e), "regime": "ERROR"}
