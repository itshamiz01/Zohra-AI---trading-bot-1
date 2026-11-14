"""Test a spoken joke request, not the user's hardware microphone."""
import asyncio
import audioop
import io
import json
import uuid
import wave

import websockets
from zohra.services.voice.tts_connector import TTSConnector


async def main():
    request_audio = TTSConnector().synthesize("Tell me a short joke in English, please.", "friendly")
    with wave.open(io.BytesIO(request_audio)) as wav:
        pcm = wav.readframes(wav.getnframes())
        if wav.getnchannels() == 2:
            pcm = audioop.tomono(pcm, wav.getsampwidth(), 0.5, 0.5)
        if wav.getsampwidth() != 2:
            pcm = audioop.lin2lin(pcm, wav.getsampwidth(), 2)
        pcm, _ = audioop.ratecv(pcm, 2, 1, wav.getframerate(), 16000, None)
    url = "ws://127.0.0.1:8011/api/v1/voice/stream?session_id=audio-" + uuid.uuid4().hex
    async with websockets.connect(url, origin="http://127.0.0.1:8011", max_size=4 * 1024 * 1024) as socket:
        await socket.send(json.dumps({"type": "speech_started"}))
        await socket.send(pcm)
        await socket.send(json.dumps({"type": "speech_stopped", "control_only": False}))
        transcript, reply, audio_bytes = "", "", 0
        while True:
            event = await asyncio.wait_for(socket.recv(), 120)
            if isinstance(event, bytes):
                audio_bytes += len(event)
                continue
            event = json.loads(event)
            if event["type"] == "transcript":
                transcript = event["content"]
            elif event["type"] == "token":
                reply += event["content"]
            elif event["type"] == "error":
                print("ERROR", event["content"], flush=True)
            elif event["type"] == "response_done":
                break
        assert transcript and reply and audio_bytes and "unavailable right now" not in reply
        assert "joke" in transcript.lower()
        print(json.dumps({"transcript": transcript, "reply": reply, "audio_bytes": audio_bytes}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
