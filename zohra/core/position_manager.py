"""
╔══════════════════════════════════════════════════════╗
║         ZOHRA — ADAPTIVE POSITION MANAGER            ║
║  A+/A/B Quality-Based Trade Management              ║
║  Ported from trading_bot2, upgraded for MT5          ║
╚══════════════════════════════════════════════════════╝

Management logic per quality grade:
  A+ → Let winners run, trail at 1R, close only at structural break
  A  → Close 50% at 1.5R, trail rest, BE at 0.8R
  B  → Close 50% at 1R, close full at 2R, BE early

Exits triggered by:
  - R multiple targets
  - Momentum stall (ADX < 20)
  - Price stall (3 bars tight range)
  - Volume drop
"""

import logging
from typing import Optional, Dict
import pandas as pd
import numpy as np

logger = logging.getLogger("zohra.manager")


class PositionManager:
    """
    Adaptive trade manager — broker agnostic.
    Returns ACTION strings; calling code sends orders to MT5.

    Actions returned:
      HOLD        → Do nothing
      MOVE_BE     → Move SL to entry (breakeven)
      CLOSE_HALF  → Close 50% of position
      CLOSE_FULL  → Close entire position
      TRAIL       → Trail stop loss (new_stop provided)
    """

    ADX_PERIOD   = 14
    STALL_BARS   = 3

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high_low   = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close  = (df['low']  - df['close'].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        if len(df) < period * 2:
            return 25.0  # Neutral
        plus_dm  = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm  = np.where((plus_dm  > minus_dm) & (plus_dm  > 0), plus_dm,  0)
        minus_dm = np.where((minus_dm > plus_dm)  & (minus_dm > 0), minus_dm, 0)
        high_low   = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift(1)).abs()
        low_close  = (df['low']  - df['close'].shift(1)).abs()
        atr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(period).mean()
        plus_di  = 100 * pd.Series(plus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9)
        minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period).mean() / (atr + 1e-9)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9)
        adx = dx.rolling(period).mean()
        return float(adx.iloc[-1]) if not adx.empty else 25.0

    def _is_stalling(self, df: pd.DataFrame) -> bool:
        """Detect 3+ consecutive bars with tight range (< 50% of avg range)"""
        if len(df) < self.STALL_BARS + 5:
            return False
        recent_range = (df['high'] - df['low']).tail(self.STALL_BARS + 5)
        avg_range    = recent_range.mean()
        last_bars    = recent_range.tail(self.STALL_BARS)
        return (last_bars < avg_range * 0.5).all()

    def _r_multiple(self, trade: Dict, current_price: float) -> float:
        """Calculate current profit in R multiples."""
        entry    = trade['entry_price']
        stop     = trade['stop_loss']
        direction = trade['direction']
        risk = abs(entry - stop)
        if risk == 0:
            return 0.0
        if direction == "LONG":
            return (current_price - entry) / risk
        else:
            return (entry - current_price) / risk

    def manage(self, trade: Dict, df: pd.DataFrame) -> Dict:
        """
        Evaluate a trade and return management action.

        Args:
            trade: dict with keys: direction, entry_price, stop_loss,
                   take_profit, quality (A+/A/B), be_moved, scale_out_level (0-3)
            df:    current OHLCV dataframe

        Returns:
            dict: {
                'action': str,          # HOLD / MOVE_BE / CLOSE_HALF / CLOSE_PARTIAL / CLOSE_FULL / TRAIL
                'new_stop': float,      # for TRAIL action
                'reason': str,
                'r_multiple': float,
            }
        """
        if df is None or df.empty:
            return {'action': 'HOLD', 'reason': 'No data', 'r_multiple': 0}

        current  = float(df.iloc[-1]['close'])
        r        = self._r_multiple(trade, current)
        quality  = trade.get('quality', 'B')
        be_moved = trade.get('be_moved', False)
        scale_out_level = trade.get('scale_out_level', 0)
        atr      = self._calculate_atr(df)
        adx      = self._calculate_adx(df)
        stalling = self._is_stalling(df)

        result = {'action': 'HOLD', 'reason': '', 'r_multiple': round(r, 3),
                  'new_stop': trade.get('stop_loss')}

        direction = trade['direction']

        # ─── A+ GRADE: Let winners run ──────────────────────
        if quality == "A+":
            if r >= 2.5 and scale_out_level < 2:
                result['action'] = 'CLOSE_PARTIAL'
                result['reason'] = f"A+: Stage 2 scale-out (25%) at {r:.1f}R"
            elif r >= 1.5 and scale_out_level < 1:
                result['action'] = 'CLOSE_HALF'
                result['reason'] = f"A+: Stage 1 scale-out (50%) at {r:.1f}R"
            elif r >= 1.0:
                if not be_moved:
                    result.update({'action': 'MOVE_BE', 'reason': f"A+: Move to BE at {r:.1f}R"})
                elif scale_out_level >= 2:
                    # Trail aggressively after Stage 2 scale-out
                    new_stop = (current - atr * 1.0) if direction == "LONG" else (current + atr * 1.0)
                    if self._stop_improves(trade, new_stop):
                        result.update({'action': 'TRAIL', 'new_stop': round(new_stop, 5),
                                       'reason': f"A+: Trail at {r:.1f}R"})
            elif r < -0.5 and stalling:
                result.update({'action': 'CLOSE_FULL', 'reason': "A+: Stalling below -0.5R"})

        # ─── A GRADE: Standard management ───────────────────
        elif quality == "A":
            if r >= 2.5 and scale_out_level < 2:
                result['action'] = 'CLOSE_PARTIAL'
                result['reason'] = f"A: Stage 2 scale-out (25%) at {r:.1f}R"
            elif r >= 1.5 and scale_out_level < 1:
                result.update({'action': 'CLOSE_HALF', 'reason': f"A: Stage 1 scale-out (50%) at {r:.1f}R"})
            elif r >= 0.8 and not be_moved:
                result.update({'action': 'MOVE_BE', 'reason': f"A: Move to BE at {r:.1f}R"})
            elif r >= 1.5 and scale_out_level >= 1 and adx > 25:
                new_stop = (current - atr * 1.5) if direction == "LONG" else (current + atr * 1.5)
                if self._stop_improves(trade, new_stop):
                    result.update({'action': 'TRAIL', 'new_stop': round(new_stop, 5),
                                   'reason': f"A: Trail at {r:.1f}R"})
            elif r < -0.3 and adx < 20:
                result.update({'action': 'CLOSE_FULL', 'reason': "A: Momentum gone, close"})

        # ─── B GRADE: Secure profit early ───────────────────
        elif quality == "B":
            if r >= 1.0 and scale_out_level < 1:
                result.update({'action': 'CLOSE_HALF', 'reason': f"B: Secure 50% at {r:.1f}R"})
            elif r >= 0.5 and not be_moved:
                result.update({'action': 'MOVE_BE', 'reason': f"B: Move to BE at {r:.1f}R"})
            elif r >= 2.0:
                result.update({'action': 'CLOSE_FULL', 'reason': "B: Full close at 2.0R"})
            elif r < 0 and (stalling or adx < 20):
                result.update({'action': 'CLOSE_FULL', 'reason': "B: Negative + stalling, exit"})

        # ─── Universal: Momentum stall exit ─────────────────
        if result['action'] == 'HOLD':
            if adx < 20 and r > 0.5:
                result.update({'action': 'CLOSE_FULL', 'reason': f"Momentum fading (ADX={adx:.1f}), lock in profit"})
            elif stalling and r < 0:
                result.update({'action': 'CLOSE_FULL', 'reason': "Price stalling in loss, cut"})

        return result

    def _stop_improves(self, trade: Dict, new_stop: float) -> bool:
        """Check if new_stop is an improvement (further from entry)."""
        direction  = trade['direction']
        entry      = trade['entry_price']
        old_stop   = trade.get('stop_loss', 0)
        if direction == "LONG":
            return new_stop > old_stop
        else:
            return new_stop < old_stop

    def calculate_new_trail_stop(self, trade: Dict, df: pd.DataFrame,
                                  atr_multiplier: float = 1.5) -> Optional[float]:
        """Calculate trailing stop using ATR behind current price."""
        atr       = self._calculate_atr(df)
        current   = float(df.iloc[-1]['close'])
        direction = trade['direction']
        old_stop  = trade.get('stop_loss', 0)

        if direction == "LONG":
            new_stop = current - atr * atr_multiplier
            return round(new_stop, 5) if new_stop > old_stop else None
        else:
            new_stop = current + atr * atr_multiplier
            return round(new_stop, 5) if new_stop < old_stop else None


# Singleton
position_manager = PositionManager()
