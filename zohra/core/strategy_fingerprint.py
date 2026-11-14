"""
╔══════════════════════════════════════════════════════════════════════╗
║             ZOHRA — STRATEGY SIGNAL FINGERPRINTING                   ║
║         Deep Metadata & Market Thesis Isolation for XAUUSD            ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import json
import uuid
import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple


@dataclass
class StrategyFingerprint:
    """
    Rich architectural fingerprint explaining WHY a trade signal exists.
    Enables cross-bot duplicate detection and thesis verification.
    """
    signal_id: str = field(default_factory=lambda: f"SIG_{uuid.uuid4().hex[:10].upper()}")
    bot_id: str = "BOT_1_TREND"
    bot_name: str = "Bot A"
    bot_role: str = "Trend & Momentum Specialist"
    symbol: str = "XAUUSD"
    direction: str = "BUY"                  # "BUY" or "SELL"
    strategy_name: str = "EMA_PULLBACK"
    strategy_group: str = "TREND"           # TREND, MEAN_REVERSION, STRUCTURE_SMC, BREAKOUT_VOLATILITY
    trigger_type: str = "PULLBACK_CONTINUATION" # PULLBACK_CONTINUATION, EXTREME_REVERSAL, LIQUIDITY_SWEEP, BREAKOUT_EXPANSION
    market_regime: str = "TRENDING_UP"
    regime_confidence: int = 80
    timeframes: List[str] = field(default_factory=lambda: ["H1", "M15", "M5"])
    entry_price: float = 0.0
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    risk_reward: float = 1.5
    confidence_score: int = 80
    structure: str = "HH_HL"                # HH_HL, LH_LL, RANGING, SWEEP_RECLAIM, BOS, CHOCH
    volatility_state: str = "NORMAL"        # COMPRESSED, EXPANDING, NORMAL, ELEVATED
    entry_reason: List[str] = field(default_factory=list)
    timestamp_utc: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrategyFingerprint":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def build_strategy_fingerprint(
    bot_id: str,
    bot_name: str,
    bot_role: str,
    signal_data: Dict[str, Any],
    regime_report: Any,
    symbol: str = "XAUUSD"
) -> StrategyFingerprint:
    """
    Constructs a complete StrategyFingerprint from engine evaluation artifacts.
    """
    direction = signal_data.get("direction", "BUY")
    strategy_name = signal_data.get("strategy", signal_data.get("strategy_name", "UNKNOWN"))
    strategy_group = signal_data.get("strategy_group", "TREND")
    entry_price = float(signal_data.get("entry_price", signal_data.get("entry", 0.0)))
    sl = float(signal_data.get("stop_loss", signal_data.get("stop", 0.0)))
    tp = float(signal_data.get("take_profit", signal_data.get("tp", 0.0)))
    rr = float(signal_data.get("risk_reward", 1.5))
    confidence = int(signal_data.get("confidence", signal_data.get("confidence_score", 80)))
    reasons = signal_data.get("reasons", signal_data.get("entry_reason", []))

    # Derive trigger type based on strategy group / name
    strat_lower = strategy_name.lower()
    if "pullback" in strat_lower or "continuation" in strat_lower:
        trigger_type = "PULLBACK_CONTINUATION"
    elif "reversion" in strat_lower or "rsi" in strat_lower or "rejection" in strat_lower:
        trigger_type = "EXTREME_REVERSAL"
    elif "sweep" in strat_lower or "fvg" in strat_lower or "order_block" in strat_lower:
        trigger_type = "LIQUIDITY_SWEEP_IMBALANCE"
    elif "breakout" in strat_lower or "expansion" in strat_lower:
        trigger_type = "BREAKOUT_EXPANSION"
    else:
        trigger_type = "TECHNICAL_SETUP"

    # Derive market structure
    regime_val = getattr(regime_report, "regime", None)
    regime_str = regime_val.value if hasattr(regime_val, "value") else str(regime_val or "UNCLEAR")
    regime_conf = int(getattr(regime_report, "confidence", 70))
    struct_str = getattr(regime_report, "structure", "RANGING")

    # Estimate entry zone (+/- 0.75 USD on gold)
    zone_low = entry_price - 0.75 if entry_price > 0 else 0.0
    zone_high = entry_price + 0.75 if entry_price > 0 else 0.0

    return StrategyFingerprint(
        bot_id=bot_id,
        bot_name=bot_name,
        bot_role=bot_role,
        symbol=symbol,
        direction=direction,
        strategy_name=strategy_name,
        strategy_group=strategy_group,
        trigger_type=trigger_type,
        market_regime=regime_str,
        regime_confidence=regime_conf,
        entry_price=entry_price,
        entry_zone_low=zone_low,
        entry_zone_high=zone_high,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=rr,
        confidence_score=confidence,
        structure=struct_str,
        entry_reason=reasons if isinstance(reasons, list) else [str(reasons)]
    )
