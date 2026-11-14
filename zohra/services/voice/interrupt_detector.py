# ZOHRA OS — Real-time Voice Interruption Detector
import logging
import time
import asyncio
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.voice.interrupt")

# Thread-safe global flag fallback for offline/isolated runtime environments
INTERRUPT_STORE = {}

def set_tts_playing(session_id: str, playing: bool):
    INTERRUPT_STORE[session_id] = playing
    logger.debug(f"TTS playing state set to {playing} for session {session_id}")

def is_tts_currently_playing(session_id: str) -> bool:
    return INTERRUPT_STORE.get(session_id, False)

class MockVADModel:
    """Mock Voice Activity Detection (VAD) model."""
    def score(self, frame: bytes) -> float:
        if b"USER_INTERRUPTING" in frame:
            return 0.95
        # Calculate RMS energy for local VAD score simulation
        import numpy as np
        if not frame:
            return 0.0
        try:
            samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
            rms = np.sqrt(np.mean(samples**2)) if len(samples) > 0 else 0.0
            # Scale rms to VAD score [0, 1]
            return min(rms * 10.0, 1.0)
        except Exception:
            return 0.0

vad_model = MockVADModel()

class InterruptDetector:
    """
    Monitors user input stream during output speech synthesis
    and triggers immediate cross-process interruption events.
    """
    def __init__(self, vad_threshold: float = 0.6):
        self.vad_threshold = vad_threshold

    async def monitor(self, mic_stream, session_id: str):
        """Asynchronously monitors microphone frames to spot speaker interrupts."""
        logger.info(f"Interrupt detector monitoring started for session: {session_id}")
        async for frame in mic_stream:
            # Enforce real-time check path
            if is_tts_currently_playing(session_id):
                score = vad_model.score(frame)
                if score > self.vad_threshold:
                    # Set the interrupt flag locally
                    INTERRUPT_STORE[f"interrupt_flag:{session_id}"] = "1"
                    # Try setting in Redis cross-process if available
                    try:
                        import redis
                        r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=1)
                        r.setex(f"interrupt_flag:{session_id}", 5, "1")
                    except Exception:
                        pass
                    
                    # Emit event
                    await event_bus.publish("voice.interrupt.detected", {
                        "session_id": session_id,
                        "timestamp": time.time()
                    })
                    logger.info("⚡ Voice interrupt detected!")
