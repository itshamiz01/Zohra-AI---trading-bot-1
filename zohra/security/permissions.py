"""
Permission gates for high-consequence Zohra actions.

Volume 1 and Volume 5 of the Zohra AI Bible define live trade execution as a
Tier 4 action: risk approval is mandatory, but it is not sufficient by itself.
This module keeps that rule outside agent prompts so every execution path can
enforce the same boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Optional

from zohra.config import settings as config

logger = logging.getLogger("zohra.security.permissions")


class PermissionTier(IntEnum):
    READ_ONLY = 0
    REVERSIBLE_NO_CONFIRM = 1
    REVERSIBLE_CONFIRM = 2
    IRREVERSIBLE_CONFIRM = 3
    HIGH_CONSEQUENCE_FINANCIAL = 4


@dataclass
class PermissionDecision:
    approved: bool
    tier: PermissionTier
    reason: str
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "tier": int(self.tier),
            "tier_name": self.tier.name,
            "reason": self.reason,
            "audit": self.audit,
        }


class TradingPermissionGateway:
    """
    Enforces the live-trading permission boundary.

    Supported execution modes:
    - paper/backtest/simulated: allowed only for explicitly simulated brokers.
    - live: allowed only when live trading has been pre-authorized.
    """

    SIMULATED_BROKERS = {"sim", "paper", "backtest", "simulated"}
    PAPER_MODES = {"paper", "backtest", "simulated"}

    def __init__(
        self,
        execution_mode: Optional[str] = None,
        live_trading_preauthorized: Optional[bool] = None,
        preauth_token: Optional[str] = None,
    ):
        self.execution_mode = (
            execution_mode
            or getattr(config, "TRADING_EXECUTION_MODE", "paper")
            or "paper"
        ).lower()
        self.live_trading_preauthorized = (
            bool(getattr(config, "LIVE_TRADING_PREAUTHORIZED", False))
            if live_trading_preauthorized is None
            else bool(live_trading_preauthorized)
        )
        self.preauth_token = (
            preauth_token
            if preauth_token is not None
            else getattr(config, "LIVE_TRADING_PREAUTH_TOKEN", "")
        )

    def authorize_trade_execution(self, request: Dict[str, Any]) -> PermissionDecision:
        symbol = request.get("symbol", "")
        direction = request.get("direction", "")
        lots = float(request.get("lots") or 0.0)
        broker = (request.get("broker") or getattr(config, "DEFAULT_BROKER", "mt5")).lower()
        risk_approved = bool(request.get("risk_approved", False))
        consensus_status = request.get("consensus_status", "")
        supplied_token = request.get("authorization_token", "")

        audit = {
            "action": "trade_execution",
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "broker": broker,
            "execution_mode": self.execution_mode,
            "risk_approved": risk_approved,
            "consensus_status": consensus_status,
        }

        if not risk_approved:
            return self._deny("Risk Chairman approval is required before execution.", audit)

        if consensus_status and consensus_status != "APPROVED":
            return self._deny("Trading committee consensus is not approved.", audit)

        if lots <= 0:
            return self._deny("Position size must be greater than zero.", audit)

        if self.execution_mode in self.PAPER_MODES:
            if broker in self.SIMULATED_BROKERS:
                return self._approve("Simulated execution approved.", audit)
            return self._deny(
                "Paper mode is active; live broker execution is blocked. "
                "Use the simulated broker or set TRADING_EXECUTION_MODE=live with pre-authorization.",
                audit,
            )

        if self.execution_mode != "live":
            return self._deny(
                f"Unknown trading execution mode '{self.execution_mode}'.",
                audit,
            )

        if not self.live_trading_preauthorized:
            return self._deny(
                "Live trading requires explicit pre-authorization "
                "(LIVE_TRADING_PREAUTHORIZED=1).",
                audit,
            )

        if self.preauth_token and supplied_token != self.preauth_token:
            return self._deny("Live trading pre-authorization token is missing or invalid.", audit)

        return self._approve("Live trading pre-authorization accepted.", audit)

    def authorize_broker_action(self, action: str, request: Dict[str, Any], *, log_denial: bool = True) -> PermissionDecision:
        """Authorize a broker-side control action such as closing positions.

        Closing an order is financially consequential even though it does not
        create a new one.  It therefore shares the same explicit mode and
        pre-authorization boundary as order placement, while avoiding the
        artificial position-size requirement of ``authorize_trade_execution``.
        """
        broker = (request.get("broker") or getattr(config, "DEFAULT_BROKER", "mt5")).lower()
        supplied_token = request.get("authorization_token", "")
        audit = {
            "action": action,
            "broker": broker,
            "execution_mode": self.execution_mode,
        }

        if broker in self.SIMULATED_BROKERS:
            return self._approve("Simulated broker action approved.", audit)

        if self.execution_mode != "live":
            return self._deny(
                "Paper mode is active; direct broker actions are blocked. "
                "Use the simulated broker or enable live mode with pre-authorization.",
                audit,
                log_denial=log_denial,
            )
        if not self.live_trading_preauthorized:
            return self._deny("Live broker actions require explicit pre-authorization.", audit, log_denial=log_denial)
        if self.preauth_token and supplied_token != self.preauth_token:
            return self._deny("Live trading pre-authorization token is missing or invalid.", audit, log_denial=log_denial)
        return self._approve("Live broker action pre-authorization accepted.", audit)

    def _approve(self, reason: str, audit: Dict[str, Any]) -> PermissionDecision:
        logger.info("Tier 4 permission approved: %s", audit)
        return PermissionDecision(True, PermissionTier.HIGH_CONSEQUENCE_FINANCIAL, reason, audit)

    def _deny(self, reason: str, audit: Dict[str, Any], *, log_denial: bool = True) -> PermissionDecision:
        if log_denial:
            logger.warning("Tier 4 permission denied: %s | %s", reason, audit)
        return PermissionDecision(False, PermissionTier.HIGH_CONSEQUENCE_FINANCIAL, reason, audit)


trading_permission_gateway = TradingPermissionGateway()
