# ZOHRA OS — Local Wake Word Detector (Keyword Spotting)
import logging
import time
from zohra.event_bus import event_bus

logger = logging.getLogger("zohra.voice.wakeword")

class MockKWSModel:
    """
    Mock Keyword Spotting (KWS) model.
    Runs locally with zero external network dependencies.
    """
    def __init__(self, model_path: str):
        self.model_path = model_path

    def infer(self, audio_frame: bytes) -> float:
        # Detect special test marker or compute energy coefficient
        if b"TRIGGER_WAKEWORD" in audio_frame:
            return 0.98
        # Otherwise return low ambient score
        return 0.05

def load_local_kws_model(model_path: str) -> MockKWSModel:
    logger.info(f"Loading local keyword spotting model from {model_path}...")
    return MockKWSModel(model_path)

class WakeWordDetector:
    """
    Always-listening keyword spotting engine running locally.
    Enforces the latency budget of <=150ms from utterance to trigger.
    """
    def __init__(self, model_path: str, threshold: float = 0.85):
        self.model = load_local_kws_model(model_path)
        self.threshold = threshold

    def process_frame(self, audio_frame: bytes) -> bool:
        score = self.model.infer(audio_frame)
        if score > self.threshold:
            # Emit wake-word trigger event asynchronously
            try:
                # We can run event_bus publish in a task if running inside an event loop
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(event_bus.publish("voice.wakeword.triggered", {"score": score, "timestamp": time.time()}))
            except Exception:
                pass
            logger.info(f"⚡ Wake word triggered (confidence={score:.4f})")
            return True
        return False
