import asyncio
import json
from unittest.mock import MagicMock

import pytest

from zohra.services.chat import assistant_brain as brain_module
from zohra.services.chat import assistant_tools
from zohra.services.chat.assistant_store import AssistantStore
from zohra.services.voice.voice_gateway import VoiceGatewayService


def run_turn(brain, prompt="Hello", session="conversation-test"):
    async def collect():
        return [event async for event in brain.run_reasoning_loop(session, prompt)]
    return asyncio.run(collect())


def tool_call(name, arguments, call_id="call-1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def test_only_real_user_tasks_are_saved(tmp_path):
    store = AssistantStore(tmp_path / "assistant.db")
    assert store.manage_tasks()["tasks"] == []
    task = store.manage_tasks("create", "Review the weekly report")
    assert task["status"] == "created"
    assert store.manage_tasks()["pending_count"] == 1
    assert store.manage_tasks("complete", task_id=task["task_id"])["status"] == "completed"
    assert store.manage_tasks()["pending_count"] == 0
    assert len(AssistantStore(store.path).manage_tasks()["tasks"]) == 1


@pytest.mark.parametrize("args", [{"action": "delete"}, {"action": "create", "title": ""},
    {"action": "create", "title": "x" * 501}, {"action": "complete", "task_id": True},
    {"action": "complete", "task_id": "1"}])
def test_invalid_task_changes_are_rejected(tmp_path, args):
    assert "error" in AssistantStore(tmp_path / "assistant.db").manage_tasks(**args)


@pytest.mark.parametrize("name", ["close_active_positions", "modify_risk_setting", "shutdown", "run_command", "place_trade"])
def test_financial_and_os_tools_cannot_be_granted_by_model_output(name):
    assert "PERMISSION_DENIED" in assistant_tools.execute_tool(name, {"role": "owner"})["error"]


def test_backend_snapshot_preserves_unavailable_data(monkeypatch):
    from zohra.analytics import telemetry_provider
    monkeypatch.setattr(telemetry_provider, "get_trading_telemetry", lambda: {
        "status": "STALE", "balance": None, "recorded_at": "old"})
    result = assistant_tools.get_backend_update("trading")
    assert result["source"] == "/api/v1/os/telemetry"
    assert result["data"]["status"] == "STALE"
    assert result["data"]["balance"] is None


def test_backend_failures_are_not_invented(monkeypatch):
    def fail(**args):
        raise RuntimeError("offline")
    monkeypatch.setattr(assistant_tools, "get_backend_update", fail)
    assert "unavailable" in assistant_tools.execute_tool("get_backend_update", {"domain": "system"})["error"]


def test_multi_turn_context_is_saved_without_duplicating_current_prompt(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    requests = []
    def respond(messages):
        requests.append(list(messages))
        return {"content": "Of course, I remember."}
    monkeypatch.setattr(brain, "_request", respond)
    run_turn(brain, "My name is Sam")
    run_turn(brain, "What is my name?")
    assert [m["content"] for m in requests[1] if m["role"] == "user"] == ["My name is Sam", "What is my name?"]
    assert len(brain.store.history("conversation-test")) == 4
    assert brain.store.history("different-session") == []


def test_private_action_history_stays_local_and_does_not_leak_to_other_chat_provider(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path / "assistant.db")
    store.add_message("conversation-test", "user", "My name is Sam")
    store.add_message("conversation-test", "user", "write file with private chapter material", private_context=True)
    store.add_message("conversation-test", "assistant", "Private account balance: 1234", private_context=True)
    brain = brain_module.AssistantBrain(store)
    captured = []
    def reply(messages):
        captured.extend(messages)
        return {"content": "Hello Sam."}
    monkeypatch.setattr(brain, "_request", reply)
    run_turn(brain, "Hello")
    assert any(row["content"] == "My name is Sam" for row in captured)
    assert not any("private chapter" in row["content"] or "1234" in row["content"] for row in captured)
    assert any("1234" in row["content"] for row in store.history("conversation-test"))


def test_legacy_private_backend_turn_is_not_reused_in_unrelated_chat(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path / "assistant.db")
    brain = brain_module.AssistantBrain(store)
    responses = iter([{ "tool_calls": [tool_call("get_backend_update", {"domain":"trading"})]},
                      {"content":"Private account snapshot: 98765"}, {"content":"A short joke."}])
    requests = []
    def reply(messages):
        requests.append(list(messages))
        return next(responses)
    monkeypatch.setattr(brain, "_request", reply)
    monkeypatch.setattr(brain_module, "execute_tool", lambda *args: {"data":{"balance":98765}})
    run_turn(brain, "Read trading status")
    run_turn(brain, "Tell a joke")
    assert not any("98765" in row["content"] for row in requests[-1])
    assert any("98765" in row["content"] for row in store.history("conversation-test"))


def test_real_task_tool_loop_and_permission_boundary(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    replies = iter([
        {"tool_calls": [tool_call("manage_tasks", {"action": "create", "title": "Call Alex"})]},
        {"tool_calls": [tool_call("close_active_positions", {"action_type": "ALL"}, "call-2")]},
        {"content": "Task changes require dashboard confirmation. Trading actions are unavailable."},
    ])
    requests = []
    def respond(messages):
        requests.append(list(messages))
        return next(replies)
    monkeypatch.setattr(brain, "_request", respond)
    events = run_turn(brain, "Save a task to call Alex")
    assert brain.store.manage_tasks()["tasks"] == []
    observations = [json.loads(m["content"]) for m in requests[-1] if m["role"] == "tool"]
    assert "CONFIRMATION_REQUIRED" in observations[0]["error"]
    assert "PERMISSION_DENIED" in observations[1]["error"]
    assert "confirmation" in "".join(e["content"] for e in events if e["type"] == "token")


def test_provider_failure_never_uses_legacy_command_dispatch(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    def fail(messages):
        raise ConnectionError("offline")
    monkeypatch.setattr(brain, "_request", fail)
    events = run_turn(brain, "Close every position now")
    assert any(e["type"] == "error" for e in events)
    assert brain.store.manage_tasks()["tasks"] == []


def test_retired_free_model_uses_only_same_provider_free_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(brain_module.settings, "CHAT_PROVIDER", "openrouter")
    monkeypatch.setattr(brain_module.settings, "OPENROUTER_MODEL", "retired/model:free")
    monkeypatch.setattr(brain_module.settings, "OPENROUTER_API_KEY", "test-key")
    models = []
    def post(url, headers, json, timeout):
        models.append(json["model"])
        response = MagicMock(status_code=404 if len(models) == 1 else 200)
        response.json.return_value = {"choices": [{"message": {"content": "Hello"}}]}
        return response
    monkeypatch.setattr(brain_module.requests, "post", post)
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    assert brain._request([])["content"] == "Hello"
    assert brain._request([])["content"] == "Hello"
    assert models == ["retired/model:free", "openrouter/free", "openrouter/free"]
    assert brain_module.settings.OPENROUTER_MODEL == "retired/model:free"


def test_full_response_secrets_are_redacted_before_token_chunking(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    secret = "sk-or-v1-" + "x" * 40
    monkeypatch.setattr(brain, "_request", lambda messages: {"content": "Here is " + secret})
    reply = "".join(e["content"] for e in run_turn(brain) if e["type"] == "token")
    assert secret not in reply
    assert "[secret redacted]" in reply


@pytest.mark.parametrize("typed", [False, True])
def test_voice_and_typed_updates_reach_real_assistant_without_keyword_auth(monkeypatch, typed):
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    gateway.stt = MagicMock()
    gateway.stt.transcribe.return_value = "Give me a trading account update"
    gateway.speaker_id = MagicMock()
    gateway.speaker_id.identify_speaker.return_value = ("Guest", 0, "guest")
    gateway.voice_memory = MagicMock()
    gateway.voice_memory.apply_pronunciation.side_effect = lambda text: text
    gateway.tts = MagicMock()
    gateway.tts.synthesize.return_value = b"RIFF-audio"
    prompts, messages, audio = [], [], []
    async def reason(session, prompt):
        prompts.append((session, prompt))
        yield {"type": "acknowledgement", "content": "Let me check the available update."}
        yield {"type": "sources", "sources": [{"title": "NASA", "url": "https://www.nasa.gov/"}]}
        yield {"type": "token", "content": "The account snapshot is unavailable."}
    from zohra.services.chat import assistant_orchestrator
    monkeypatch.setattr(assistant_orchestrator, "voice_events", reason)
    class Socket:
        async def send_text(self, text):
            messages.append(json.loads(text))
        async def send_bytes(self, data):
            audio.append(data)
    text = "Give me a trading account update" if typed else None
    asyncio.run(gateway._generate_and_stream_response(Socket(), "assistant-test", b"pcm", text_input=text))
    assert prompts == [("assistant-test", "Give me a trading account update")]
    gateway.speaker_id.voice_authenticate.assert_not_called()
    assert audio == [b"RIFF-audio", b"RIFF-audio"]
    assert next(i for i, message in enumerate(messages) if message["type"] == "acknowledgement") < next(
        i for i, message in enumerate(messages) if message["type"] == "token")
    assert {"type": "response_done"} in messages
    assert any(message["type"] == "sources" for message in messages)
    if typed:
        gateway.stt.transcribe.assert_not_called()
        gateway.speaker_id.identify_speaker.assert_not_called()


def test_gateway_validates_typed_messages_and_routes_valid_text():
    gateway = VoiceGatewayService.__new__(VoiceGatewayService)
    processed, errors = [], []
    async def process(*args, **kwargs):
        processed.append(kwargs["text_input"])
    gateway._generate_and_stream_response = process
    class Socket:
        events = iter([{"text": json.dumps({"type": "text_input", "content": []})},
            {"text": json.dumps({"type": "text_input", "content": "x" * 4001})},
            {"text": json.dumps({"type": "text_input", "content": "  Hello  "})},
            {"type": "websocket.disconnect"}])
        async def receive(self):
            await asyncio.sleep(0)
            return next(self.events)
        async def send_text(self, text):
            errors.append(json.loads(text))
    asyncio.run(gateway.process_voice_stream(Socket(), "assistant-test"))
    assert processed == ["Hello"]
    assert len([m for m in errors if m["type"] == "error"]) == 2


@pytest.mark.parametrize("url,origin", [
    ("/api/v1/voice/stream?session_id=test", "https://unrelated.example"),
    ("/api/v1/voice/stream?session_id=../../other", "http://testserver"),
])
def test_voice_connection_rejects_cross_origin_and_invalid_session_ids(url, origin):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from zohra.api.voice_router import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(url, headers={"origin": origin}):
                pass
    assert rejected.value.code == 1008
