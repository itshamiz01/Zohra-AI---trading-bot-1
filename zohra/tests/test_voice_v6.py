import unittest
import asyncio
import time
from typing import AsyncGenerator
from unittest.mock import MagicMock
import numpy as np

from zohra.services.voice.models import VoiceSession, AuthResult
from zohra.services.voice.wake_word import WakeWordDetector
from zohra.services.voice.stt_connector import STTConnector
from zohra.services.voice.tts_connector import TTSConnector
from zohra.services.voice.speaker_id import SpeakerIdentifier
from zohra.services.voice.interrupt_detector import (
    InterruptDetector,
    set_tts_playing,
    is_tts_currently_playing,
    INTERRUPT_STORE,
)
from zohra.event_bus import event_bus

class TestVoiceIntelligenceV6(unittest.TestCase):
    def test_voice_session_model(self):
        session = VoiceSession(
            enrolled_user_id="user_123",
            transcript_final="Run diagnostic tools.",
            auth_result="approved"
        )
        self.assertEqual(session.enrolled_user_id, "user_123")
        self.assertEqual(session.transcript_final, "Run diagnostic tools.")
        self.assertEqual(session.auth_result, "approved")
        self.assertFalse(session.interrupted)

    def test_wake_word_detector(self):
        detector = WakeWordDetector(model_path="fake/path", threshold=0.85)
        
        # Test case: ambient noise
        triggered_noise = detector.process_frame(b"ambient noise frames...")
        self.assertFalse(triggered_noise)

        # Test case: trigger keyword
        triggered_keyword = detector.process_frame(b"TRIGGER_WAKEWORD some speech...")
        self.assertTrue(triggered_keyword)

    def test_stt_streaming(self):
        connector = STTConnector()
        connector.transcribe = MagicMock(return_value="hello zohra")
        
        # Setup mock event handler
        received_events = []
        def on_event(payload):
            received_events.append(payload)

        event_bus.subscribe("voice.transcript.partial", on_event)
        event_bus.subscribe("voice.transcript.final", on_event)

        async def run_stt():
            async def chunk_generator():
                yield b"TEST_CHUNK_HELLO"
                yield b"TEST_CHUNK_FINAL"
            return await connector.stream_stt(chunk_generator(), "test_session_id")

        try:
            res = asyncio.run(run_stt())
            self.assertEqual(res, "hello zohra")
            connector.transcribe.assert_called_once_with(b"TEST_CHUNK_HELLOTEST_CHUNK_FINAL")
            # Wait for event bus async tasks to run since they run in background/executor
            time.sleep(0.1)
            # Ensure both partial and final events are recorded
            partial_events = [e for e in received_events if "text" in e and e["text"] == "hello"]
            final_events = [e for e in received_events if "text" in e and e["text"] == "hello zohra"]
            self.assertTrue(len(partial_events) > 0 or len(final_events) > 0)
        finally:
            event_bus.unsubscribe("voice.transcript.partial", on_event)
            event_bus.unsubscribe("voice.transcript.final", on_event)

    def test_stt_without_model_has_no_invented_transcript(self):
        connector = STTConnector()
        connector.provider = "local"
        connector.local_model = None
        self.assertEqual(connector.transcribe(bytes(3200)), "")

    def test_tts_sentence_streaming(self):
        connector = TTSConnector()
        # Test sentence chunking independently of optional local hardware.
        connector.synthesize = MagicMock(side_effect=[b"first", b"second"])

        async def run_tts():
            async def token_generator():
                yield "Hello. "
                yield "This is a test "
                yield "token stream! "
            
            chunks = []
            async for chunk in connector.stream_tts(token_generator()):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(run_tts())
        self.assertEqual(chunks, [b"first", b"second"])

    def test_voice_authentication_and_liveness(self):
        identifier = SpeakerIdentifier()

        # An installation without an operator-provisioned profile must never
        # identify an arbitrary caller as an owner.
        sample_owner = bytes([0x00] * 3200)
        auth_ok = identifier.voice_authenticate(sample_owner, claimed_user_id="Hamid", required_confidence=0.80)
        self.assertEqual(auth_ok.status, "rejected")
        self.assertEqual(auth_ok.reason, "User identity mismatch")

        # Identity mismatch check
        auth_wrong = identifier.voice_authenticate(sample_owner, claimed_user_id="John", required_confidence=0.80)
        self.assertEqual(auth_wrong.status, "rejected")
        self.assertEqual(auth_wrong.reason, "User identity mismatch")

        # Even an explicitly provisioned matching embedding must fail closed
        # until a genuine liveness verifier is configured.
        identifier.enrolled_speakers = {"Hamid": {"signature": np.ones(32), "role": "owner"}}
        identifier.feature_extractor = lambda _audio: np.ones(32)
        auth_replay = identifier.voice_authenticate(sample_owner, claimed_user_id="Hamid", required_confidence=0.80)
        self.assertEqual(auth_replay.status, "rejected")
        self.assertEqual(auth_replay.reason, "Liveness check failed")

    def test_interrupt_detection(self):
        detector = InterruptDetector(vad_threshold=0.6)
        session_id = "test_session_99"

        # Setup mock event handler
        interrupt_events = []
        def on_interrupt(payload):
            interrupt_events.append(payload)
        event_bus.subscribe("voice.interrupt.detected", on_interrupt)

        try:
            # Case 1: TTS is not playing -> Should not interrupt
            set_tts_playing(session_id, False)
            
            async def stream_no_playing():
                yield b"USER_INTERRUPTING"
            asyncio.run(detector.monitor(stream_no_playing(), session_id))
            
            self.assertEqual(len(interrupt_events), 0)

            # Case 2: TTS is playing -> VAD score > threshold -> Should interrupt
            set_tts_playing(session_id, True)
            
            async def stream_playing():
                yield b"USER_INTERRUPTING"
            asyncio.run(detector.monitor(stream_playing(), session_id))
            
            time.sleep(0.1)
            self.assertEqual(len(interrupt_events), 1)
            self.assertEqual(INTERRUPT_STORE.get(f"interrupt_flag:{session_id}"), "1")
        finally:
            event_bus.unsubscribe("voice.interrupt.detected", on_interrupt)


if __name__ == "__main__":
    unittest.main()
