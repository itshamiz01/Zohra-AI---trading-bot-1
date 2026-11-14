"""Public-search conversation smoke test; no trading or task mutations."""
import asyncio
import json
import uuid

import websockets


async def main():
    session = "search-smoke-" + uuid.uuid4().hex
    async with websockets.connect("ws://127.0.0.1:8011/api/v1/voice/stream?session_id=" + session,
            origin="http://127.0.0.1:8011", max_size=4 * 1024 * 1024) as socket:
        await socket.send(json.dumps({"type": "text_input", "content":
            "Search the web now for NASA Artemis using official NASA sources. Summarize the search excerpts in two sentences in English; do not claim you read full pages."}))
        reply, sources, tools, audio_bytes = "", [], [], 0
        sequence = []
        while True:
            data = await asyncio.wait_for(socket.recv(), 120)
            if isinstance(data, bytes):
                sequence.append("audio")
                audio_bytes += len(data)
                continue
            event = json.loads(data)
            sequence.append(event["type"])
            if event["type"] == "token":
                reply += event["content"]
            elif event["type"] == "sources":
                sources = event["sources"]
            elif event["type"] == "tool":
                tools.append(event["name"])
            elif event["type"] == "error":
                raise AssertionError(event["content"])
            elif event["type"] == "response_done":
                break
        print(json.dumps({"reply": reply, "sources": sources, "tools": tools,
                          "female_voice_audio_bytes": audio_bytes}), flush=True)
        assert "search_web" in tools and sources and audio_bytes > 0
        assert sequence.index("acknowledgement") < sequence.index("audio") < sequence.index("tool")
        assert "https://" not in reply
        await socket.send(json.dumps({"type": "history"}))
        while True:
            event = json.loads(await asyncio.wait_for(socket.recv(), 30))
            if event["type"] == "history":
                assert event["messages"][-1]["sources"] == sources
                break
        print(json.dumps({"reply": reply, "sources": sources, "tools": tools,
                          "female_voice_audio_bytes": audio_bytes, "source_history_preserved": True}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
