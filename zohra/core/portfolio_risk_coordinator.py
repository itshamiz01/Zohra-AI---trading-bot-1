"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — PORTFOLIO RISK COORDINATOR                      ║
║     Central Multi-Bot Exposure Protection & Duplicate Arbiter        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import os
import logging
import time
import datetime as dt
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

from zohra.core.strategy_fingerprint import StrategyFingerprint
from zohra.core.cross_bot_signal_registry import cross_bot_signal_registry

logger = logging.getLogger("zohra.portfolio_risk")


@dataclass
class PortfolioApprovalResult:
    """Outcome of Portfolio Risk Coordinator validation."""
    approved: bool
    action: str                         # "APPROVE", "REDUCE_SIZE", "REJECT"
    adjusted_lot_multiplier: float = 1.0 # 1.0 = normal, 0.5 = reduced, 0.0 = rejected
    duplicate_score: int = 0
    duplicate_classification: str = "INDEPENDENT"
    rejection_reason: str = ""
    active_fleet_positions: int = 0
    total_fleet_exposure_lots: float = 0.0
    audit_notes: List[str] = field(default_factory=list)


class PortfolioRiskCoordinator:
    """
    Central Portfolio Risk Engine that governs total risk across all 3 ZOHRA bots.
    Ensures:
      1. Aggregate XAUUSD position limits across all MT5 terminals.
      2. Duplicate signal rejection (score >= 61).
      3. Preservation of genuine independent trade theses.
      4. Strict prohibition of forced opposite trading.
    """

    def __init__(self, shared_dir: Optional[str] = None):
        if shared_dir:
            self.shared_dir = shared_dir
        else:
            from zohra.config.settings import CROSS_BOT_LOG_DIR
            self.shared_dir = CROSS_BOT_LOG_DIR

        os.makedirs(self.shared_dir, exist_ok=True)
        self.state_file = os.path.join(self.shared_dir, "active_portfolio_state.json")

        # Global Fleet Exposure Caps (Across all 3 bots combined)
        self.max_fleet_open_positions: int = 4
        self.max_fleet_exposure_lots: float = 0.10
        self.duplicate_rejection_threshold: int = 61
        self.moderate_overlap_threshold: int = 31

        logger.info(f"🛡️ PortfolioRiskCoordinator active. State file: {self.state_file}")

    def _load_fleet_state(self) -> Dict[str, Any]:
        """Loads aggregate position state across all 3 bot instances and purges stale entries."""
        if not os.path.exists(self.state_file):
            return {"active_positions": {}, "last_updated": ""}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Reconcile / purge entries older than 2 hours or invalid
            active = data.get("active_positions", {})
            now = dt.datetime.now(dt.timezone.utc)
            valid_active = {}
            for k, v in active.items():
                try:
                    opened_str = v.get("opened_at", "")
                    if opened_str:
                        op_dt = dt.datetime.fromisoformat(opened_str.replace("Z", "+00:00"))
                        if (now - op_dt).total_seconds() > 7200: # 2 hours max lifetime
                            continue
                    valid_active[k] = v
                except Exception:
                    continue
            if len(valid_active) != len(active):
                data["active_positions"] = valid_active
                self._save_fleet_state(data)
            return data
        except Exception:
            return {"active_positions": {}, "last_updated": ""}

    def _save_fleet_state(self, state: Dict[str, Any]):
        """Persists aggregate position state."""
        try:
            state["last_updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving fleet portfolio state: {e}")

    def register_open_position(self, bot_id: str, ticket: int, symbol: str,
                               direction: str, lots: float, strategy: str, entry_price: float):
        """Records a new open trade into the central fleet state."""
        state = self._load_fleet_state()
        pos_id = f"{bot_id}_{ticket}"
        state["active_positions"][pos_id] = {
            "bot_id": bot_id,
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "lots": lots,
            "strategy": strategy,
            "entry_price": entry_price,
            "opened_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        self._save_fleet_state(state)
        logger.info(f"🛡️ Registered position #{ticket} for {bot_id} ({lots}L {direction} {symbol}) in Portfolio Risk Engine.")

    def register_closed_position(self, bot_id: str, ticket: int):
        """Removes a closed trade from central fleet state."""
        state = self._load_fleet_state()
        pos_id = f"{bot_id}_{ticket}"
        if pos_id in state["active_positions"]:
            del state["active_positions"][pos_id]
            self._save_fleet_state(state)
            logger.info(f"🛡️ Position #{ticket} for {bot_id} closed & cleared from Portfolio Risk Engine.")

    def evaluate_execution_approval(
        self,
        fingerprint: StrategyFingerprint,
        requested_lots: float = 0.01
    ) -> PortfolioApprovalResult:
        """
        Main gatekeeper evaluated by each bot before placing an order on MetaTrader 5.
        Checks:
          1. Cross-bot duplicate exposure score (0-100)
          2. Aggregate fleet position count
          3. Total fleet XAUUSD lot allocation
        """
        audit_notes = []

        # 1. Publish candidate signal to shared registry
        cross_bot_signal_registry.publish_signal(fingerprint)

        # 2. Compute Duplicate Exposure Score
        dup_score, dup_reason, overlaps = cross_bot_signal_registry.calculate_duplicate_exposure_score(
            candidate=fingerprint,
            window_seconds=300,
            price_proximity_usd=1.50
        )

        audit_notes.append(f"Duplicate Score: {dup_score}/100 ({dup_reason})")

        # 3. Read current fleet active exposure
        fleet_state = self._load_fleet_state()
        active_pos = fleet_state.get("active_positions", {})
        fleet_pos_count = len(active_pos)
        fleet_total_lots = sum(float(p.get("lots", 0.01)) for p in active_pos.values())

        # Clean out stale positions older than 8 hours if orphaned
        now = dt.datetime.now(dt.timezone.utc)
        stale_keys = []
        for k, p in active_pos.items():
            try:
                op_time = dt.datetime.fromisoformat(p.get("opened_at", ""))
                if op_time.tzinfo is None: op_time = op_time.replace(tzinfo=dt.timezone.utc)
                if (now - op_time).total_seconds() > 28800:
                    stale_keys.append(k)
            except Exception:
                pass
        for k in stale_keys:
            del active_pos[k]

        # 4. Check Aggregate Fleet Position Cap
        if fleet_pos_count >= self.max_fleet_open_positions:
            rejection = f"FLEET_MAX_OPEN_POSITIONS_REACHED ({fleet_pos_count} >= {self.max_fleet_open_positions})"
            logger.warning(f"🚨 [{fingerprint.bot_id}] Portfolio Risk VETO: {rejection}")
            return PortfolioApprovalResult(
                approved=False,
                action="REJECT",
                adjusted_lot_multiplier=0.0,
                duplicate_score=dup_score,
                duplicate_classification=dup_reason,
                rejection_reason=rejection,
                active_fleet_positions=fleet_pos_count,
                total_fleet_exposure_lots=fleet_total_lots,
                audit_notes=audit_notes
            )

        # 5. Check Aggregate Fleet Lot Exposure Cap
        if fleet_total_lots + requested_lots > self.max_fleet_exposure_lots:
            rejection = f"FLEET_MAX_EXPOSURE_LOTS_EXCEEDED ({fleet_total_lots + requested_lots:.2f}L > {self.max_fleet_exposure_lots:.2f}L)"
            logger.warning(f"🚨 [{fingerprint.bot_id}] Portfolio Risk VETO: {rejection}")
            return PortfolioApprovalResult(
                approved=False,
                action="REJECT",
                adjusted_lot_multiplier=0.0,
                duplicate_score=dup_score,
                duplicate_classification=dup_reason,
                rejection_reason=rejection,
                active_fleet_positions=fleet_pos_count,
                total_fleet_exposure_lots=fleet_total_lots,
                audit_notes=audit_notes
            )

        # 6. Check High Duplicate Exposure (Score >= 61)
        if dup_score >= self.duplicate_rejection_threshold:
            # High duplicate — check if peer has an active position
            has_active_peer_in_same_trade = False
            for p in active_pos.values():
                if (p.get("direction") == fingerprint.direction and
                        abs(float(p.get("entry_price", 0)) - fingerprint.entry_price) <= 1.50):
                    has_active_peer_in_same_trade = True
                    break

            if has_active_peer_in_same_trade:
                rejection = f"HIGH_DUPLICATE_EXPOSURE_ACTIVE (Score={dup_score}>={self.duplicate_rejection_threshold}: Peer bot already open in identical price zone)"
                logger.warning(f"🚨 [{fingerprint.bot_id}] Portfolio Risk VETO: {rejection}")
                return PortfolioApprovalResult(
                    approved=False,
                    action="REJECT",
                    adjusted_lot_multiplier=0.0,
                    duplicate_score=dup_score,
                    duplicate_classification=dup_reason,
                    rejection_reason=rejection,
                    active_fleet_positions=fleet_pos_count,
                    total_fleet_exposure_lots=fleet_total_lots,
                    audit_notes=audit_notes
                )

        # 7. Moderate Overlap (Score 31-60) -> Approved with 50% Position Sizing
        if dup_score >= self.moderate_overlap_threshold:
            logger.info(f"⚠️ [{fingerprint.bot_id}] Moderate Overlap Detected (Score={dup_score}). Approving with 50% position scaling.")
            audit_notes.append("Approved with 50% lot multiplier due to moderate overlap.")
            return PortfolioApprovalResult(
                approved=True,
                action="REDUCE_SIZE",
                adjusted_lot_multiplier=0.5,
                duplicate_score=dup_score,
                duplicate_classification=dup_reason,
                rejection_reason="",
                active_fleet_positions=fleet_pos_count,
                total_fleet_exposure_lots=fleet_total_lots,
                audit_notes=audit_notes
            )

        # 8. Full Approval — Independent Signal
        logger.info(f"✅ [{fingerprint.bot_id}] Independent Signal Approved (Duplicate Score: {dup_score}/100). Full lot allocation.")
        return PortfolioApprovalResult(
            approved=True,
            action="APPROVE",
            adjusted_lot_multiplier=1.0,
            duplicate_score=dup_score,
            duplicate_classification=dup_reason,
            rejection_reason="",
            active_fleet_positions=fleet_pos_count,
            total_fleet_exposure_lots=fleet_total_lots,
            audit_notes=audit_notes
        )


# Master singleton instance
portfolio_risk_coordinator = PortfolioRiskCoordinator()
