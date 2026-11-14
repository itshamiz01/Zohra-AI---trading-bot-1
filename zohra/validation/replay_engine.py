"""
╔══════════════════════════════════════════════════════════════════════╗
║              ZOHRA — MARKET REPLAY ENGINE                           ║
║     Historical Tick/OHLC Playback & AI Decision Re-evaluation        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pandas as pd

logger = logging.getLogger("zohra.validation.replay")


class MarketReplayEngine:
    """
    Simulates historical time ticks step-by-step to replay market crashes,
    high volatility events, and verify how the AI decisions would respond.
    """

    def __init__(self):
        self.active_df: Optional[pd.DataFrame] = None
        self.symbol = ""
        self.current_idx = 0
        self.is_paused = True
        self.speed_multiplier = 1.0  # seconds between ticks in real world

        # Events presets
        self.presets = {
            "2008_crash": {"start": "2008-09-14", "end": "2008-09-20", "symbol": "US500"},
            "covid_crash": {"start": "2020-03-08", "end": "2020-03-16", "symbol": "US500"},
            "brexit_vote": {"start": "2016-06-22", "end": "2016-06-25", "symbol": "GBPUSD"},
            "swiss_peg": {"start": "2015-01-14", "end": "2015-01-16", "symbol": "EURCHF"},
        }

    def load_preset(self, preset_name: str, df_provider: Optional[pd.DataFrame] = None) -> bool:
        """Loads a preset historical event into replay buffer."""
        if preset_name not in self.presets:
            logger.warning(f"Replay preset {preset_name} not found.")
            return False
        
        preset = self.presets[preset_name]
        self.symbol = preset["symbol"]
        self.current_idx = 0
        self.is_paused = True

        if df_provider is not None:
            self.active_df = df_provider
            return True
            
        # Standard mock generator for offline replays
        self._generate_preset_mock(preset_name)
        return True

    def configure_replay(self, df: pd.DataFrame, symbol: str):
        """Configure custom replay session."""
        self.active_df = df
        self.symbol = symbol
        self.current_idx = 0
        self.is_paused = True

    # ─── Playback Controls ────────────────────────────────────

    def play(self):
        self.is_paused = False
        logger.info(f"▶ [Replay Engine] Playback started for {self.symbol}.")

    def pause(self):
        self.is_paused = True
        logger.info(f"⏸ [Replay Engine] Playback paused.")

    def set_speed(self, speed: float):
        self.speed_multiplier = speed
        logger.info(f"⏩ [Replay Engine] Playback speed set to {speed}x.")

    def step_forward(self) -> Optional[Dict[str, Any]]:
        """Steps forward by 1 bar."""
        if self.active_df is None or self.current_idx >= len(self.active_df) - 1:
            return None
        self.current_idx += 1
        return self._get_current_bar_data()

    def step_backward(self) -> Optional[Dict[str, Any]]:
        """Steps backward by 1 bar."""
        if self.active_df is None or self.current_idx <= 0:
            return None
        self.current_idx -= 1
        return self._get_current_bar_data()

    def jump_to_time(self, timestamp: datetime) -> bool:
        """Jump cursor to a specific date in the buffer."""
        if self.active_df is None:
            return False
        
        # Check indices closest to timestamp
        times = self.active_df.index
        best_idx = 0
        min_diff = timedelta(days=999)
        for i, t in enumerate(times):
            diff = abs(t - timestamp)
            if diff < min_diff:
                min_diff = diff
                best_idx = i
                
        self.current_idx = best_idx
        return True

    # ─── Playback Data Retrieval ──────────────────────────────

    def get_visible_history(self) -> Optional[pd.DataFrame]:
        """Returns the slice of the dataframe visible to the strategy (up to current index)."""
        if self.active_df is None:
            return None
        return self.active_df.iloc[:self.current_idx + 1]

    def _get_current_bar_data(self) -> Dict[str, Any]:
        """Fetch details of the bar at current cursor index."""
        row = self.active_df.iloc[self.current_idx]
        return {
            "index": self.current_idx,
            "total_bars": len(self.active_df),
            "timestamp": self.active_df.index[self.current_idx].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("tick_volume", row.get("volume", 0))),
        }

    # ─── Mock Generator for Offline Presets ───────────────────

    def _generate_preset_mock(self, preset_name: str):
        import numpy as np
        preset = self.presets[preset_name]
        start = datetime.strptime(preset["start"], "%Y-%m-%d")
        end = datetime.strptime(preset["end"], "%Y-%m-%d")
        
        hours = int((end - start).total_seconds() / 3600)
        times = [start + timedelta(hours=i) for i in range(hours)]
        
        # Drawdown/crash pattern
        np.random.seed(42)
        base = 1500.0 if preset["symbol"] == "US500" else 1.4500
        
        # Build price collapse
        prices = []
        cur = base
        for i in range(hours):
            pct_change = np.random.normal(-0.002, 0.005) # downward drift
            if i > hours // 3 and i < hours * 2 // 3:
                pct_change = np.random.normal(-0.015, 0.012) # extreme crash window
            cur = cur * (1 + pct_change)
            prices.append(cur)

        prices = np.array(prices)
        open_ = np.roll(prices, 1)
        open_[0] = base
        high = np.maximum(open_, prices) + (base * 0.001)
        low = np.minimum(open_, prices) - (base * 0.001)

        self.active_df = pd.DataFrame({
            "open": open_,
            "high": high,
            "low": low,
            "close": prices,
            "tick_volume": np.random.randint(1000, 5000, size=hours)
        }, index=times)


# Singleton
replay_engine = MarketReplayEngine()
