import asyncio
import json
from unittest.mock import MagicMock

import pytest

from zohra.services.voice.portrait_commands import portrait_command
from zohra.services.voice.voice_gateway import VoiceGatewayService


@pytest.mark.parametrize("phrase", ["over", "OVER!", "\u0913\u0935\u0930",
    "now you can go", "Okay, now you can go.", "ok over"])
def test_explicit_dismissal(phrase):
    assert portrait_command(phrase) == "hide"


@pytest.mark.parametrize("phrase", ["move over there", "go over the trades",
    "the market is over", "go", "", None])
def test_no_substring_dismissal(phrase):
    assert portrait_command(phrase) is None


@pytest.mark.parametrize("phrase,control_only,expected", [
    ("over", False, "hide"), ("\u0913\u0935\u0930", True, "hide"),
    ("Okay now you can go", True, "hide"), ("buy gold", True, None),
])
def test_commands_and_sound_only_input_never_reach_reasoning_or_tts(phrase, control_only, expected):
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    gateway.stt = MagicMock()
    gateway.stt.transcribe.return_value = phrase
    gateway.speaker_id = MagicMock()
    gateway.speaker_id.identify_speaker.return_value = ("Guest", 0.0, "guest")
    gateway.tts = MagicMock()
    messages = []

    class Socket:
        async def send_text(self, text):
            messages.append(json.loads(text))

    asyncio.run(gateway._generate_and_stream_response(Socket(), "portrait-test", bytes(3200),
        control_only=control_only))
    assert {"type": "transcript", "content": phrase} in messages
    actions = [message for message in messages if message["type"] == "portrait"]
    assert actions == ([{"type": "portrait", "action": expected}] if expected else [])
    assert not any(message.get("content") == "THINKING" for message in messages)
    gateway.tts.synthesize.assert_not_called()
    gateway.speaker_id.voice_authenticate.assert_not_called()


def test_socket_passes_control_only_flag_to_audio_processing():
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    processed = []

    async def process(socket, session, audio, control_only=False):
        processed.append((audio, control_only))

    gateway._generate_and_stream_response = process

    class Socket:
        events = iter([{"bytes": b"pcm"}, {"text": json.dumps({"type": "speech_stopped", "control_only": True})},
            {"type": "websocket.disconnect"}])

        async def send_text(self, text):
            pass

        async def receive(self):
            await asyncio.sleep(0)
            return next(self.events)

    asyncio.run(gateway.process_voice_stream(Socket(), "portrait-test"))
    assert processed == [(b"pcm", True)]


def test_portrait_hidden_cancels_active_reply_and_discards_pending_audio():
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    cancelled = []
    statuses = []

    async def process(*args, **kwargs):
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    gateway._generate_and_stream_response = process

    class Socket:
        events = iter([{"bytes": b"pcm"}, {"text": json.dumps({"type": "speech_stopped"})},
            {"bytes": b"stale"}, {"text": json.dumps({"type": "portrait_hidden"})},
            {"text": json.dumps({"type": "speech_stopped"})}, {"type": "websocket.disconnect"}])

        async def send_text(self, text):
            statuses.append(json.loads(text))

        async def receive(self):
            await asyncio.sleep(0)
            return next(self.events)

    asyncio.run(gateway.process_voice_stream(Socket(), "portrait-cancellation"))
    assert cancelled == [True]
    assert {"type": "interrupt", "content": "STOP_PLAYBACK"} in statuses
    assert {"type": "error", "content": "EMPTY_AUDIO_BUFFER"} in statuses
