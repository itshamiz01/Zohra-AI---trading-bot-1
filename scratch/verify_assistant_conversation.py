"""Harmless local preview smoke test: no financial or personal-task mutations."""
import asyncio
import json
import uuid
from pathlib import Path

import requests
import websockets


async def main():
    session = "smoke-" + uuid.uuid4().hex
    url = "ws://127.0.0.1:8011/api/v1/voice/stream?session_id=" + session
    async with websockets.connect(url, origin="http://127.0.0.1:8011", max_size=4 * 1024 * 1024) as socket:
        for prompt in ["Hello Zohra. My nickname for this test is Nova. Reply briefly in English.",
                       "What was my nickname for this test? Reply briefly in English.",
                       "Give me the actual current system CPU and memory usage briefly in English."]:
            await socket.send(json.dumps({"type": "text_input", "content": prompt}))
            reply, tools, audio_bytes = "", [], 0
            while True:
                data = await asyncio.wait_for(socket.recv(), 120)
                if isinstance(data, bytes):
                    if not audio_bytes:
                        Path("scratch/assistant-live-reply.wav").write_bytes(data)
                    audio_bytes += len(data)
                    continue
                event = json.loads(data)
                if event["type"] == "token":
                    reply += event["content"]
                elif event["type"] == "tool":
                    tools.append(event["name"])
                elif event["type"] == "error":
                    print("ERROR", event["content"], flush=True)
                elif event["type"] == "response_done":
                    print(json.dumps({"reply": reply, "tools": tools, "audio_bytes": audio_bytes}), flush=True)
                    break
    report = requests.get("http://127.0.0.1:8011/api/v1/voice/diagnostics", timeout=30).json()
    print(json.dumps(report.get("diagnostics", {}).get("components", {})), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
