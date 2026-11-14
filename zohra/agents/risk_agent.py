import logging
from datetime import datetime
from typing import Dict, List, Tuple, Any
from zohra.core.agent_message import AgentMessage
from zohra.core.enums import TradeQuality
from zohra.brokers.mt5_broker import mt5_broker
from zohra.core.signal_scorer import scorer
from zohra.config.settings import (
    RISK_PER_TRADE_PCT, MAX_OPEN_POSITIONS, MAX_LOT_SIZE, MIN_LOT_SIZE,
    MAX_DAILY_TRADES, MAX_SECTOR_POSITIONS, MAX_CURRENCY_EXPOSURE, STATE
)
from zohra.core.symbol_manager import symbol_manager
from zohra.core.correlation_engine import correlation_engine

logger = logging.getLogger("zohra.risk_agent")

class RiskAgent:
    """
    Risk Management Agent:
    - Performs portfolio-level exposure calculations.
    - Limits exposure by trading sector (Forex, Metals, Indices).
    - Caps currency exposure (e.g., maximum USD positions).
    - Vetoes highly correlated setups using the correlation engine.
    - Monitors account drawdowns and daily trade counts.
    """
    def __init__(self, starting_equity: float = 0.0):
        self.starting_equity = starting_equity

    def evaluate_portfolio_risk(self, symbol: str, lots: float, open_positions: List[Dict], direction: str) -> Tuple[bool, str]:
        """
        Runs comprehensive portfolio safety checks before approving a trade.
        Returns (approved: bool, reason: str)
        """
        # 0. Central Hard Symbol Guard
        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return False, f"Hard symbol guard: Symbol '{symbol}' is not allowed (only Gold/Silver permitted)."

        # 1. Total Open Positions Cap
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            return False, f"Maximum active positions limit ({MAX_OPEN_POSITIONS}) reached."

        # 2. Daily Execution Trade Count Cap
        if STATE.daily_trades >= MAX_DAILY_TRADES:
            return False, f"Daily execution trade count limit ({MAX_DAILY_TRADES}) reached."

        # 3. Lot Bounds Check
        if lots < MIN_LOT_SIZE or lots > MAX_LOT_SIZE:
            return False, f"Lots calculation {lots} is outside bounds [{MIN_LOT_SIZE}, {MAX_LOT_SIZE}]."

        # 4. Sector Exposure Check
        params = symbol_manager.get_symbol_params(symbol)
        if not params:
            return False, f"Symbol {symbol} parameter registry missing."
        
        sector = params.get("sector", "Forex")
        max_sector_cap = MAX_SECTOR_POSITIONS.get(sector, 3)
        
        current_sector_count = 0
        for pos in open_positions:
            pos_symbol = pos["symbol"]
            pos_params = symbol_manager.get_symbol_params(pos_symbol)
            if pos_params and pos_params.get("sector") == sector:
                current_sector_count += 1
                
        if current_sector_count >= max_sector_cap:
            return False, f"Sector exposure cap for {sector} ({max_sector_cap}) reached."

        # 5. Currency Stack Check
        # Only applies to Forex — Metals (XAUUSD/XAGUSD) are exempt because they are an
        # independent asset class and should not count against the forex USD exposure bucket.
        if sector != "Metals" and "USD" in symbol:
            usd_exposure_count = 0
            for pos in open_positions:
                if "USD" in pos["symbol"]:
                    usd_exposure_count += 1
            if usd_exposure_count >= MAX_CURRENCY_EXPOSURE:
                return False, f"Currency exposure cap for USD ({MAX_CURRENCY_EXPOSURE}) reached. Skip to prevent stacking."

        # 6. Correlation Engine Check
        # Metals are exempt — Gold/Silver correlations with forex pairs are structurally
        # different and the correlation engine is calibrated for forex, not commodities.
        if sector != "Metals" and open_positions:
            for pos in open_positions:
                other_sym = pos["symbol"]
                other_dir = pos.get("direction", "LONG")

                coeff = correlation_engine.get_correlation(symbol, other_sym)

                # Check if correlation is high.
                # If same direction, high positive correlation (> 0.75) is a risk.
                # If opposite directions, high negative correlation (< -0.75) is also a risk.
                is_same_dir = (direction == other_dir)
                if is_same_dir and coeff >= 0.75:
                    return False, f"VETO: Correlation with open position {other_sym} is too high ({coeff:.2f})."
                elif not is_same_dir and coeff <= -0.75:
                    return False, f"VETO: Inverse correlation with open position {other_sym} is too high ({coeff:.2f})."

        return True, "Portfolio risk checks passed."

    def evaluate_proposal(self, message: AgentMessage) -> AgentMessage:
        """
        Kept for backward compatibility and test compliance.
        """
        payload = message.payload
        symbol = payload.get("symbol", "EURUSD")
        proposal_id = message.message_id
        entry = payload.get("entry_price", 0.0)
        sl = payload.get("stop_loss", 0.0)
        score = payload.get("confidence_score", 0)
        direction = payload.get("direction", "LONG")

        # Get current equity from broker
        from zohra.config.settings import VIRTUAL_EQUITY_OVERRIDE
        if VIRTUAL_EQUITY_OVERRIDE is not None:
            equity = VIRTUAL_EQUITY_OVERRIDE
        else:
            equity = mt5_broker.get_equity()
            
        if self.starting_equity == 0.0 or VIRTUAL_EQUITY_OVERRIDE is not None:
            if VIRTUAL_EQUITY_OVERRIDE is not None:
                self.starting_equity = VIRTUAL_EQUITY_OVERRIDE
            else:
                account_info = mt5_broker.get_account_info()
                if account_info:
                    self.starting_equity = account_info.get("balance", equity)
        
        # Scorer contains kill switch check
        blocked, kill_reason = scorer.check_kill_switch(equity, self.starting_equity)
        if blocked:
            return AgentMessage(
                sender="RiskAgent",
                message_type="VOTE",
                payload={
                    "proposal_id": proposal_id,
                    "vote": "VETO",
                    "lots": 0.0,
                    "reason": f"Risk limits exceeded: {kill_reason}"
                }
            )

        # Sizing mapping
        if score >= 90:
            grade = TradeQuality.A_PLUS
        elif score >= 80:
            grade = TradeQuality.A
        elif score >= 70:
            grade = TradeQuality.B
        elif score >= 60:
            grade = TradeQuality.C
        else:
            grade = TradeQuality.REJECT

        from zohra.config.settings import ALLOW_C_SETUPS, STATE
        if STATE.peak_equity <= 0.0:
            STATE.peak_equity = max(STATE.session_equity, equity)
        else:
            STATE.peak_equity = max(STATE.peak_equity, equity)

        drawdown_pct = max(0.0, (STATE.peak_equity - equity) / STATE.peak_equity * 100.0) if STATE.peak_equity > 0 else 0.0

        if grade == TradeQuality.REJECT:
            return AgentMessage(
                sender="RiskAgent",
                message_type="VOTE",
                payload={
                    "proposal_id": proposal_id,
                    "vote": "VETO",
                    "lots": 0.0,
                    "reason": f"Trade score {score} resolves to grade REJECT (below 60)."
                }
            )

        if grade == TradeQuality.C and not ALLOW_C_SETUPS:
            return AgentMessage(
                sender="RiskAgent",
                message_type="VOTE",
                payload={
                    "proposal_id": proposal_id,
                    "vote": "VETO",
                    "lots": 0.0,
                    "reason": f"Trade score {score} resolves to grade C, which is disabled by configuration (ALLOW_C_SETUPS=False)."
                }
            )

        if drawdown_pct > 8.0:
            return AgentMessage(
                sender="RiskAgent",
                message_type="VOTE",
                payload={
                    "proposal_id": proposal_id,
                    "vote": "VETO",
                    "lots": 0.0,
                    "reason": f"Trading paused: session drawdown ({drawdown_pct:.1f}%) exceeds safety limit of 8.0%."
                }
            )

        stop_dist = abs(entry - sl)
        lots = scorer.get_position_size(grade, equity, stop_dist, symbol, drawdown_pct)
        if lots <= 0:
            lots = MIN_LOT_SIZE
            
        lots = min(lots, MAX_LOT_SIZE)
        lots = max(lots, MIN_LOT_SIZE)
        lots = round(lots, 2)

        open_positions = mt5_broker.get_open_positions()
        allowed, reason = self.evaluate_portfolio_risk(symbol, lots, open_positions, direction)
        
        if not allowed:
            return AgentMessage(
                sender="RiskAgent",
                message_type="VOTE",
                payload={
                    "proposal_id": proposal_id,
                    "vote": "VETO",
                    "lots": 0.0,
                    "reason": reason
                }
            )

        return AgentMessage(
            sender="RiskAgent",
            message_type="VOTE",
            payload={
                "proposal_id": proposal_id,
                "vote": "APPROVE",
                "lots": lots,
                "reason": f"Portfolio and trade checks approved. Lots: {lots}. {reason}"
            }
        )
