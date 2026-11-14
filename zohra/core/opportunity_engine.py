import logging
import datetime as dt
from typing import Dict, List, Optional
from zohra.core.enums import StrategyName

logger = logging.getLogger("zohra.opportunity_engine")

class OpportunityEngine:
    """
    Ranks, scores, and categorizes active setups.
    Generates dynamic leaderboards to identify high-probability setups.
    """
    def __init__(self, expiry_minutes: int = 15):
        self.expiry_minutes = expiry_minutes
        self.active_setups: Dict[str, Dict] = {} # key is symbol + strategy

    def register_setup(self, setup: Dict):
        symbol = setup["symbol"]
        strategy = setup["strategy"]

        from zohra.core.symbol_resolver import symbol_resolver
        if not symbol_resolver.is_symbol_allowed(symbol):
            logger.warning(f"BLOCKED: Trading not allowed for {symbol}")
            return

        key = f"{symbol}_{strategy}"
        
        # Keep track of setup creation time
        setup["registered_at"] = dt.datetime.now(dt.timezone.utc)
        self.active_setups[key] = setup
        logger.info(f"📋 Leaderboard registered setup: {symbol} | Strategy={strategy} | Score={setup['confidence_score']}")
        
        try:
            from zohra.db.schema import db
            # Serialize datetime to isoformat before saving
            opp_serialized = []
            for opp in self.get_leaderboard():
                opp_copy = opp.copy()
                opp_copy["timestamp"] = opp_copy["registered_at"].isoformat()
                opp_serialized.append(opp_copy)
            db.save_live_opportunities(opp_serialized)
        except Exception as e:
            logger.error(f"Error saving to DB: {e}")

    def _prune_expired_setups(self):
        now = dt.datetime.now(dt.timezone.utc)
        keys_to_delete = []
        for key, setup in self.active_setups.items():
            age = (now - setup["registered_at"]).total_seconds() / 60.0
            if age > self.expiry_minutes:
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del self.active_setups[key]

    def get_leaderboard(self) -> List[Dict]:
        """Returns sorted list of active, unexpired opportunities."""
        self._prune_expired_setups()
        sorted_setups = sorted(
            self.active_setups.values(),
            key=lambda x: x["confidence_score"],
            reverse=True
        )
        return sorted_setups

    def get_top_opportunity(self) -> Optional[Dict]:
        leaderboard = self.get_leaderboard()
        return leaderboard[0] if leaderboard else None

    def get_top_scalping_opportunity(self) -> Optional[Dict]:
        leaderboard = self.get_leaderboard()
        for setup in leaderboard:
            if setup["strategy"] in (StrategyName.SCALP_M5.value, StrategyName.MEAN_REVERSION.value):
                return setup
        return None

    def get_top_swing_opportunity(self) -> Optional[Dict]:
        leaderboard = self.get_leaderboard()
        for setup in leaderboard:
            if setup["strategy"] == StrategyName.ZOHRA_V5.value:
                return setup
        return None

    def get_top_trend_opportunity(self) -> Optional[Dict]:
        leaderboard = self.get_leaderboard()
        for setup in leaderboard:
            if "trend" in setup["strategy"].lower() or "following" in setup["strategy"].lower():
                return setup
        return None

    def get_top_reversal_opportunity(self) -> Optional[Dict]:
        leaderboard = self.get_leaderboard()
        for setup in leaderboard:
            if "reversal" in setup["strategy"].lower() or "mean" in setup["strategy"].lower():
                return setup
        return None

    def remove_setup(self, symbol: str, strategy: str):
        key = f"{symbol}_{strategy}"
        if key in self.active_setups:
            del self.active_setups[key]
            try:
                from zohra.db.schema import db
                opp_serialized = []
                for opp in self.get_leaderboard():
                    opp_copy = opp.copy()
                    opp_copy["timestamp"] = opp_copy["registered_at"].isoformat()
                    opp_serialized.append(opp_copy)
                db.save_live_opportunities(opp_serialized)
            except Exception as e:
                logger.error(f"Error saving to DB: {e}")
