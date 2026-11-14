"""
╔══════════════════════════════════════════════════════════════════════╗
║                    ZOHRA — MARKET REPLAY LAB                         ║
║        Historical Playback, Manual Control, and Shadow Replay        ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import logging
import asyncio
import pandas as pd
from typing import Dict, List, Optional, Callable

logger = logging.getLogger("zohra.replay")

class MarketReplayLab:
    """
    Simulates a virtual trading room environment for historical data replay.
    Supports playback controls, speed scaling, and strategy/Shadow AI evaluation.
    """
    def __init__(self):
        self.df: Optional[pd.DataFrame] = None
        self.current_idx = 0
        self.is_playing = False
        self.speed_multiplier = 1.0 # 1.0 = 1 second per bar
        self.on_bar_callback: Optional[Callable[[pd.DataFrame, int], None]] = None

    def load_data(self, df: pd.DataFrame):
        """Loads historical DataFrame for replay."""
        self.df = df
        self.current_idx = 0
        self.is_playing = False
        logger.info(f"🎞️ Replay Lab: Loaded {len(df)} historical bars.")

    def play(self, callback: Callable[[pd.DataFrame, int], None] = None):
        """Starts playback."""
        if self.df is None:
            logger.error("No data loaded in Replay Lab.")
            return
        
        self.is_playing = True
        if callback:
            self.on_bar_callback = callback
        
        asyncio.create_task(self._playback_loop())
        logger.info("🎞️ Replay Lab: Playback started.")

    def pause(self):
        """Pauses playback."""
        self.is_playing = False
        logger.info("🎞️ Replay Lab: Playback paused.")

    def step_forward(self):
        """Steps forward by one bar."""
        if self.df is None or self.current_idx >= len(self.df) - 1:
            return
        self.current_idx += 1
        self._trigger_callback()
        logger.info(f"🎞️ Replay Lab: Stepped forward to index {self.current_idx}.")

    def step_backward(self):
        """Steps backward by one bar."""
        if self.df is None or self.current_idx <= 0:
            return
        self.current_idx -= 1
        self._trigger_callback()
        logger.info(f"🎞️ Replay Lab: Stepped backward to index {self.current_idx}.")

    def set_speed(self, multiplier: float):
        """Sets playback speed multiplier (e.g. 2.0 = twice as fast)."""
        self.speed_multiplier = max(0.1, multiplier)
        logger.info(f"🎞️ Replay Lab: Speed multiplier set to {self.speed_multiplier}x.")

    def _trigger_callback(self):
        """Triggers the callback with the historical slice up to current_idx."""
        if self.df is not None and self.on_bar_callback:
            # Slice up to current index to prevent lookahead bias
            sliced_df = self.df.iloc[:self.current_idx + 1]
            try:
                self.on_bar_callback(sliced_df, self.current_idx)
            except Exception as e:
                logger.error(f"Error in Replay Lab callback: {e}")

    async def _playback_loop(self):
        """Internal asynchronous playback loop."""
        while self.is_playing and self.df is not None:
            if self.current_idx >= len(self.df) - 1:
                logger.info("🎞️ Replay Lab: End of historical data reached.")
                self.is_playing = False
                break

            self.current_idx += 1
            self._trigger_callback()

            # Calculate sleep duration based on speed multiplier
            sleep_dur = 1.0 / self.speed_multiplier
            await asyncio.sleep(sleep_dur)

# Singleton
market_replay_lab = MarketReplayLab()
