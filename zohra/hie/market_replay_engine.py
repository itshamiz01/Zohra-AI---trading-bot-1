"""
╔══════════════════════════════════════════════════════════════════════╗
║   MODULE 2 — MARKET REPLAY ENGINE                                    ║
║   Simulates historical market movement candle-by-candle.             ║
║   Zohra CANNOT see future candles during replay.                     ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import time
import logging
import threading
import datetime as dt
from typing import Optional, Dict, Any

import pandas as pd

logger = logging.getLogger("zohra.hie.replay")

# Speed multipliers → sleep between candles (seconds)
REPLAY_SPEEDS = {
    "1x":   60.0,    # Real-time M1
    "5x":   12.0,
    "10x":  6.0,
    "50x":  1.2,
    "100x": 0.6,
    "MAX":  0.0      # No sleep — instant scan
}


class MarketReplaySession:
    """
    A single replay session for one symbol / timeframe window.
    Future candles are strictly hidden — Zohra only sees data up to current_index.
    """

    def __init__(
        self,
        session_id: str,
        symbol: str,
        timeframe: str,
        from_dt: str,
        to_dt: str,
        speed: str = "10x"
    ):
        self.session_id = session_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.from_dt = from_dt
        self.to_dt = to_dt
        self.speed = speed
        self.sleep_sec = REPLAY_SPEEDS.get(speed, 6.0)

        self._candles: pd.DataFrame = pd.DataFrame()
        self._index: int = 0
        self._running: bool = False
        self._paused: bool = False
        self._thread: Optional[threading.Thread] = None
        self._on_candle_callbacks = []
        self._loaded = False

    def load(self) -> bool:
        """Load candles from historical data engine. Returns True if data available."""
        try:
            from zohra.hie.historical_data_engine import historical_data_engine
            df = historical_data_engine.get_candles(
                self.symbol, self.timeframe, self.from_dt, self.to_dt, limit=50000
            )
            if df.empty:
                logger.warning(f"Replay {self.session_id}: No candles found for {self.symbol}/{self.timeframe}")
                return False
            self._candles = df
            self._index = 0
            self._loaded = True
            logger.info(f"🎬 Replay {self.session_id}: Loaded {len(df)} candles for {self.symbol}/{self.timeframe}")
            return True
        except Exception as e:
            logger.error(f"Replay load error: {e}")
            return False

    def get_visible_candles(self) -> pd.DataFrame:
        """Return candles visible at current replay position (no lookahead)."""
        if self._candles.empty:
            return pd.DataFrame()
        return self._candles.iloc[:self._index + 1].copy()

    def get_current_candle(self) -> Optional[Dict]:
        """Return the current (latest visible) candle as a dict."""
        if self._candles.empty or self._index >= len(self._candles):
            return None
        row = self._candles.iloc[self._index]
        return {
            "timestamp": str(self._candles.index[self._index]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0)),
            "candle_index": self._index,
            "total_candles": len(self._candles),
            "progress_pct": round(self._index / max(len(self._candles) - 1, 1) * 100, 1)
        }

    def advance(self) -> bool:
        """Move to next candle. Returns False if replay is complete."""
        if self._index < len(self._candles) - 1:
            self._index += 1
            return True
        return False

    def start_auto(self):
        """Start automatic candle advancement in background thread."""
        if self._running or not self._loaded:
            return
        self._running = True
        self._thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._thread.start()

    def _auto_loop(self):
        while self._running:
            if not self._paused:
                candle = self.get_current_candle()
                for cb in self._on_candle_callbacks:
                    try:
                        cb(candle)
                    except Exception:
                        pass
                if not self.advance():
                    self._running = False
                    logger.info(f"🎬 Replay {self.session_id}: Complete.")
                    break
            if self.sleep_sec > 0:
                time.sleep(self.sleep_sec)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False

    def seek(self, index: int):
        """Jump to a specific candle index."""
        if 0 <= index < len(self._candles):
            self._index = index

    def get_status(self) -> Dict:
        return {
            "session_id": self.session_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "speed": self.speed,
            "loaded": self._loaded,
            "running": self._running,
            "paused": self._paused,
            "current_index": self._index,
            "total_candles": len(self._candles),
            "progress_pct": round(self._index / max(len(self._candles) - 1, 1) * 100, 1),
            "current_timestamp": str(self._candles.index[self._index]) if self._loaded and self._index < len(self._candles) else None,
            "from_dt": self.from_dt,
            "to_dt": self.to_dt,
        }


class MarketReplayEngine:
    """
    Manages multiple concurrent replay sessions.
    Sessions are identified by session_id.
    """

    def __init__(self):
        self._sessions: Dict[str, MarketReplaySession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        symbol: str,
        timeframe: str,
        from_dt: str,
        to_dt: Optional[str] = None,
        speed: str = "10x"
    ) -> Dict:
        """
        Create and load a new replay session.

        Args:
            symbol: e.g. "EURUSD"
            timeframe: e.g. "H1"
            from_dt: ISO start datetime string
            to_dt: ISO end datetime string (default: now)
            speed: "1x", "5x", "10x", "50x", "100x", "MAX"

        Returns:
            dict with session_id and status
        """
        import uuid
        if to_dt is None:
            to_dt = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

        session_id = f"replay_{uuid.uuid4().hex[:8]}"
        session = MarketReplaySession(session_id, symbol, timeframe, from_dt, to_dt, speed)

        if not session.load():
            return {"success": False, "error": "No historical data available for the requested period."}

        with self._lock:
            self._sessions[session_id] = session

        return {"success": True, "session_id": session_id, "status": session.get_status()}

    def start_session(self, session_id: str) -> Dict:
        """Start automatic replay for session."""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        session.start_auto()
        return {"success": True, "status": session.get_status()}

    def get_next_candle(self, session_id: str) -> Dict:
        """Manually advance session by one candle and return it."""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        candle = session.get_current_candle()
        advanced = session.advance()
        return {"success": True, "candle": candle, "has_more": advanced}

    def get_visible_candles(self, session_id: str, limit: int = 200) -> Dict:
        """Return all candles visible so far in the replay (no lookahead)."""
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "candles": []}
        df = session.get_visible_candles().tail(limit)
        records = []
        for ts, row in df.iterrows():
            records.append({
                "timestamp": str(ts),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0))
            })
        return {"success": True, "candles": records, "count": len(records)}

    def pause_session(self, session_id: str) -> Dict:
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        session.pause()
        return {"success": True, "status": session.get_status()}

    def resume_session(self, session_id: str) -> Dict:
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        session.resume()
        return {"success": True, "status": session.get_status()}

    def stop_session(self, session_id: str) -> Dict:
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        session.stop()
        with self._lock:
            self._sessions.pop(session_id, None)
        return {"success": True, "message": f"Session {session_id} stopped."}

    def seek_session(self, session_id: str, index: int) -> Dict:
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        session.seek(index)
        return {"success": True, "candle": session.get_current_candle()}

    def get_session_status(self, session_id: str) -> Dict:
        session = self._get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        return {"success": True, "status": session.get_status()}

    def list_sessions(self) -> Dict:
        with self._lock:
            sessions = {sid: s.get_status() for sid, s in self._sessions.items()}
        return {"sessions": sessions, "count": len(sessions)}

    def _get_session(self, session_id: str) -> Optional[MarketReplaySession]:
        with self._lock:
            return self._sessions.get(session_id)

    def get_available_speeds(self) -> list:
        return list(REPLAY_SPEEDS.keys())


# Singleton
market_replay_engine = MarketReplayEngine()
