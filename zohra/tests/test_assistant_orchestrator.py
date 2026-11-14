"""Exercise the HTTP surface with the real Node runtime, never a trading executor."""
import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zohra.api.assistant_router import router
from zohra.api import assistant_router as api_module
from zohra.api.chat_router import router as legacy_router
from zohra.services.chat import assistant_orchestrator as orchestrator
from zohra.services.chat import assistant_brain as brain_module
from zohra.services.chat.assistant_store import AssistantStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE", str(tmp_path / "runtime"))
    store = AssistantStore(tmp_path / "history.db")
    monkeypatch.setattr(orchestrator, "assistant_store", store)
    monkeypatch.setattr(api_module, "assistant_store", store)
    monkeypatch.setattr(brain_module.assistant_brain, "store", store)
    monkeypatch.setattr(brain_module.assistant_brain, "_request", lambda messages: {"content": "Grounded test reply."})
    monkeypatch.setattr(orchestrator, "execute_tool", lambda name, args: {"source": "test-source", "data": {"cpu": 12}, "observed_at": "test-time"})
    app = FastAPI()
    @app.middleware("http")
    async def loopback_test_transport(request, call_next):
        request.scope["client"] = ("127.0.0.1", 50000)
        return await call_next(request)
    app.include_router(router)
    app.include_router(legacy_router)
    with TestClient(app, base_url="http://127.0.0.1") as connected:
        yield connected


def send(client, text, session="test"):
    response = client.post("/api/v1/assistant/message", json={"session_id": session, "message": text})
    assert response.status_code == 200
    return response.json()


def test_file_confirmation_real_executor_and_reload(client, tmp_path):
    result = send(client, 'write file "notes.md" with approved contents')
    target = tmp_path / "runtime" / "files" / "notes.md"
    assert not target.exists()
    assert result["status"] == "pending_confirmation"
    history = client.get("/api/v1/assistant/history?session_id=test").json()
    assert history["pending"]["id"] == result["pending"]["id"]
    payload = {"session_id": "test", "confirmation_id": result["pending"]["id"], "decision": True}
    assert client.post("/api/v1/assistant/confirm", json=payload).json()["status"] == "success"
    assert target.read_text() == "approved contents"
    repeat = client.post("/api/v1/assistant/confirm", json=payload).json()
    assert repeat["status"] == "failed"
    assert repeat["error"]["code"] == "STALE_CONFIRMATION"


def test_separate_yes_real_tasks_and_cancel(client):
    assert send(client, "add task read a chapter")["status"] == "pending_confirmation"
    assert send(client, "list my tasks")["data"] == []
    assert send(client, "confirm")["status"] == "failed"
    send(client, "add task read a chapter")
    assert send(client, "yes")["status"] == "success"
    assert send(client, "list my tasks")["data"][0]["title"] == "read a chapter"
    send(client, "complete task 1")
    assert send(client, "cancel")["status"] == "cancelled"
    assert send(client, "list my tasks")["data"][0]["status"] == "pending"


@pytest.mark.parametrize("text,lane", [("Show CPU usage", "TASK"), ("Show open trading positions", "TRADING"),
    ("Hello", "CHAT"), ("Line edit my chapter", "WRITING")])
def test_lanes_have_real_audit_completion(client, tmp_path, text, lane):
    result = send(client, text)
    assert result["lane"] == lane
    if lane == "TRADING":
        assert "unverified" in result["response"]
        assert result["data"]["observed_at"] == "test-time"
    with sqlite3.connect(tmp_path / "runtime" / "assistant-runtime.db") as db:
        status = db.execute("SELECT status FROM audit WHERE lane=? ORDER BY id DESC LIMIT 1", (lane,)).fetchone()[0]
    assert status == result["status"]
    messages = client.get("/api/v1/assistant/history?session_id=test").json()["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == text
    assert messages[1]["content"] == result["response"]


def test_real_error_is_reported_and_audited(client, tmp_path):
    send(client, "complete task 999")
    result = send(client, "confirm")
    assert result["status"] == "failed"
    assert "TASK_NOT_FOUND" in result["response"]
    with sqlite3.connect(tmp_path / "runtime" / "assistant-runtime.db") as db:
        error = db.execute("SELECT error FROM audit WHERE status='failed' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert json.loads(error)["code"] == "TASK_NOT_FOUND"


def test_real_provider_failure_not_success(client, monkeypatch):
    def fail(messages):
        raise ConnectionError("test provider offline")
    monkeypatch.setattr(brain_module.assistant_brain, "_request", fail)
    result = send(client, "Hello")
    assert result["status"] == "failed"
    assert "test provider offline" in result["error"]["message"]


def test_account_queries_never_send_private_observations_to_external_llm(client, monkeypatch):
    def forbidden(messages):
        raise AssertionError("Private backend state must not be transmitted")
    monkeypatch.setattr(brain_module.assistant_brain, "_request", forbidden)
    result = send(client, "Show open trading positions")
    assert result["status"] == "success"
    assert result["data"]["observed_at"] == "test-time"


def test_legacy_endpoints_cannot_bypass_gate(client):
    result = client.post("/api/v1/chat/message", json={"session_id": "test", "message": "modify risk to 0.4%"}).json()
    assert result["status"] == "blocked"
    assert result["intent"] == "TRADING"
    result = client.post("/api/v1/chat/stream", json={"session_id": "test", "message": "Add task call Alex"})
    assert "pending_confirmation" in result.text
    assert send(client, "list my tasks")["data"] == []


def test_origin_host_session_and_explicit_boolean_validation(client):
    payload = {"session_id": "test", "message": "Hello"}
    assert client.post("/api/v1/assistant/message", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/v1/assistant/message", json=payload, headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/api/v1/assistant/message", json={**payload, "session_id": "../../escape"}).status_code == 422
    assert client.post("/api/v1/assistant/confirm", json={"session_id": "test", "confirmation_id": "id", "decision": "yes"}).status_code == 422
    assert send(client, 'write file "../engine.txt" with denied')["error"]["code"] == "UNSAFE_PATH"


def test_registry_and_actual_monitoring_are_local_without_provider_calls(client, monkeypatch):
    def forbidden(messages):
        raise AssertionError("Native monitoring must not be sent to an external LLM")
    monkeypatch.setattr(brain_module.assistant_brain, "_request", forbidden)
    tools = send(client, "What can you do?")
    assert tools["status"] == "success" and tools["execution"]["tool_id"] == "capabilities.list"
    assert any(row["name"] == "android.agent" and row["availability"] == "Unsupported" for row in tools["data"]["tools"])
    processes = send(client, "Show running processes")
    assert processes["status"] == "success" and processes["data"]["process_count"] > 0
    assert processes["execution"]["verified"]
    network = send(client, "Network status")
    assert network["status"] == "success" and isinstance(network["data"]["interfaces"], list)


def test_revocation_persists_and_invalidates_another_sessions_pending_write(client, tmp_path):
    old = send(client, 'write file "revoked.txt" with should not be saved', "writer-session")
    control = client.post("/api/v1/assistant/capabilities/control", json={"session_id":"security-session", "tool_id":"files.create", "enabled":False}).json()
    assert control["status"] == "pending_confirmation"
    assert send(client, "confirm", "security-session")["data"]["verified"]
    replay = client.post("/api/v1/assistant/confirm", json={"session_id":"writer-session", "confirmation_id":old["pending"]["id"], "decision":True}).json()
    assert replay["status"] == "failed"
    assert not (tmp_path / "runtime" / "files" / "revoked.txt").exists()
    assert send(client, 'write file "new.txt" with denied')["status"] == "blocked"
    tools = client.get("/api/v1/assistant/capabilities").json()["tools"]
    assert next(row for row in tools if row["name"] == "files.create")["availability"] == "Permission Required"
    send(client, "enable tool files.create", "security-session")
    assert send(client, "confirm", "security-session")["status"] == "success"
    assert send(client, 'write file "new.txt" with allowed')["status"] == "pending_confirmation"
    assert send(client, "confirm")["execution"]["verified"]


def test_security_gate_cannot_be_disabled_and_control_types_are_strict(client):
    assert send(client, "disable tool security.configure")["status"] == "failed"
    assert send(client, "disable tool capabilities.list")["status"] == "failed"
    result = client.post("/api/v1/assistant/capabilities/control", json={"session_id":"test", "tool_id":"files.create", "enabled":"false"})
    assert result.status_code == 422


def test_execution_history_is_session_bound_and_no_raw_file_content(client):
    send(client, 'write file "private.txt" with private arbitrary note text')
    send(client, "confirm")
    events = client.get("/api/v1/assistant/activity?session_id=test").json()["events"]
    assert events[0]["status"] == "success" and events[0]["verified"]
    assert "private arbitrary note text" not in json.dumps(events)
    assert client.get("/api/v1/assistant/activity?session_id=other").json()["events"] == []
    assert client.get("/api/v1/assistant/activity?session_id=../../escape").status_code == 422


def test_remote_client_cannot_spoof_local_host():
    app = FastAPI()
    @app.middleware("http")
    async def remote_test_transport(request, call_next):
        request.scope["client"] = ("192.0.2.10", 40000)
        return await call_next(request)
    app.include_router(router)
    with TestClient(app, base_url="http://127.0.0.1") as remote:
        assert remote.get("/api/v1/assistant/capabilities").status_code == 403


def test_blocked_unrelated_request_invalidates_previous_confirmation(client, tmp_path):
    send(client, "disable tool system.processes", "security")
    assert send(client, "confirm", "security")["status"] == "success"
    send(client, 'write file "stale.txt" with must not be saved')
    assert send(client, "Show running processes")["status"] == "blocked"
    assert send(client, "confirm")["status"] == "failed"
    assert not (tmp_path / "runtime" / "files" / "stale.txt").exists()


@pytest.mark.parametrize("args", [{"volume":True}, {"volume":"25"}, {"volume":25,"device_id":"injected"}, {"volume":25,"muted":False}])
def test_windows_http_control_rejects_coercion_and_device_snapshot_injection(client, args):
    result = client.post("/api/v1/assistant/windows/control",json={"session_id":"test","action":"configure_audio","args":args})
    assert result.status_code == 422


def test_windows_status_session_and_target_are_validated(client):
    assert client.get("/api/v1/assistant/windows/status?session_id=../../escape&kind=audio").status_code == 422
    assert client.get("/api/v1/assistant/windows/status?session_id=test&kind=unknown").status_code == 422
