"""Scoped source inspection never runs code, writes files or uploads private source."""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from zohra.api import assistant_router as api_module
from zohra.services.chat import assistant_orchestrator as orchestrator
from zohra.services.chat.assistant_store import AssistantStore
from zohra.services.development.source_explain import CodeInspectionInput, inspect_code
from zohra.services.tool_execution.state import CapabilityStore


def test_actual_project_module_function_class_and_method():
    path = "zohra/services/tool_execution/catalog.py"
    module = inspect_code(path)
    assert module["kind"] == "module" and module["static_only"]
    assert any(row["name"] == "processes" for row in module["references"])
    function = inspect_code(path, "processes")
    assert function["kind"] == "function" and function["line_start"] > 0
    assert function["references"][0]["reference"] == f"{path}:{function['line_start']}"
    assert "process_iter" in function["calls"]
    path = "zohra/services/tool_execution/registry.py"
    cls = inspect_code(path, "ToolRegistry")
    assert cls["kind"] == "class" and any(row["name"] == "register" for row in cls["references"])
    method = inspect_code(path, "ToolRegistry.register")
    assert method["kind"] == "function" and method["signature"].startswith("register(self")
    assert len(method["sha256"]) == 64


@pytest.mark.parametrize("path", ["../.env", "zohra/../.env", "zohra//secret.py", "zohra/.hidden.py",
                                   "C:/Users/dell/secret.py", "zohra\\secret.py", "assistant_runtime/gate.mjs",
                                   "zohra/other.txt"])
def test_input_rejects_non_project_or_non_python_paths(path):
    with pytest.raises(ValidationError):
        CodeInspectionInput(path=path)


@pytest.mark.parametrize("symbol", ["foo()", "A.__dict__.x", "foo; rm", "a/b"])
def test_input_rejects_non_symbol_names(symbol):
    with pytest.raises(ValidationError):
        CodeInspectionInput(path="zohra/example.py", symbol=symbol)


def test_static_inspection_does_not_run_module_or_expose_literals(tmp_path):
    folder = tmp_path / "zohra"
    folder.mkdir()
    file = folder / "example.py"
    file.write_text("raise RuntimeError('EXECUTION MUST NOT HAPPEN')\nSECRET = 'not-for-output'\ndef sample(value):\n    return value\n", encoding="utf-8")
    result = inspect_code("zohra/example.py", "sample", root=tmp_path)
    assert result["static_only"] and "not-for-output" not in json.dumps(result)
    assert result["returns"] == 1
    with pytest.raises(ValueError, match="not found uniquely"):
        inspect_code("zohra/example.py", "missing", root=tmp_path)
    file.write_text("def broken(: pass", encoding="utf-8")
    with pytest.raises(ValueError, match="syntax error"):
        inspect_code("zohra/example.py", root=tmp_path)


def test_large_module_reports_full_count_with_bounded_references(tmp_path):
    folder = tmp_path / "zohra"
    folder.mkdir()
    (folder / "many.py").write_text("\n".join(f"def function_{number}(): pass" for number in range(65)), encoding="utf-8")
    result = inspect_code("zohra/many.py", root=tmp_path)
    assert "65 top-level functions" in result["summary"]
    assert len(result["references"]) == 60


def test_link_and_size_bounds(tmp_path):
    folder = tmp_path / "zohra"
    folder.mkdir()
    (folder / "large.py").write_bytes(b"#" * (128 * 1024 + 1))
    with pytest.raises(ValueError, match="128 KB"):
        inspect_code("zohra/large.py", root=tmp_path)
    outside = tmp_path / "private.py"
    outside.write_text("SECRET = 'private'", encoding="utf-8")
    link = folder / "linked.py"
    try:
        link.symlink_to(outside)
    except OSError:
        return
    with pytest.raises(ValueError, match="Linked|escapes"):
        inspect_code("zohra/linked.py", root=tmp_path)


def test_private_tool_event_does_not_publish_source_summary(tmp_path, monkeypatch):
    from zohra.services.tool_execution.catalog import get_registry
    from zohra.services.tool_execution.engine import ToolExecutor
    from zohra.services.tool_execution.models import ToolCall
    from zohra.security.permissions import PermissionTier
    from zohra.services.tool_execution import engine as engine_module

    events = []

    async def capture(event_type, payload):
        events.append((event_type, payload))

    monkeypatch.setattr(engine_module.event_bus, "publish", capture)
    call = ToolCall("coding.explain", "read", {"path":"zohra/services/tool_execution/catalog.py", "symbol":"processes"},
                    "test", PermissionTier.READ_ONLY, True)
    result = asyncio.run(ToolExecutor(get_registry(), store=CapabilityStore(tmp_path)).execute(call))
    assert result.status == "completed" and result.verified
    assert "processes()" in result.result["summary"]
    assert events[0][1]["result"]["result"] == {"redacted": True}
    assert "processes()" not in json.dumps(events)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE", str(tmp_path / "runtime"))
    history = AssistantStore(tmp_path / "history.db")
    monkeypatch.setattr(orchestrator, "assistant_store", history)
    monkeypatch.setattr(api_module, "assistant_store", history)
    app = FastAPI()

    @app.middleware("http")
    async def local_transport(request, call_next):
        request.scope["client"] = ("127.0.0.1", 50000)
        return await call_next(request)

    app.include_router(api_module.router)
    with TestClient(app, base_url="http://127.0.0.1") as connection:
        yield connection, tmp_path / "runtime"


def test_http_chat_voice_and_revocation_share_read_tool(client):
    connection, root = client
    path = "zohra/services/tool_execution/catalog.py"
    endpoint = "/api/v1/assistant/code/inspect"
    params = {"session_id":"test", "path":path, "symbol":"processes"}
    response = connection.get(endpoint, params=params)
    assert response.status_code == 200 and response.json()["verified"]
    assert response.json()["data"]["kind"] == "function"
    assert connection.get(endpoint, params={**params,"path":"zohra/../.env"}).status_code == 422
    assert connection.get(endpoint, params=params, headers={"Origin":"https://evil.example"}).status_code == 403
    text = connection.post("/api/v1/assistant/message", json={"session_id":"test",
        "message":f'explain function "processes" in "{path}"'}).json()
    assert text["status"] == "success" and text["data"]["symbol"] == "processes"

    async def spoken():
        return [event async for event in orchestrator.voice_events("test", f'explain code "{path}"')]

    voice = next(event["result"] for event in asyncio.run(spoken()) if event["type"] == "assistant_result")
    assert voice["status"] == "success" and voice["data"]["kind"] == "module"
    with CapabilityStore(root).session() as db:
        db.execute("INSERT INTO tool_controls VALUES('coding.explain',0,'now')")
    denied = connection.get(endpoint, params=params).json()
    assert denied["status"] == "blocked" and "revoked" in denied["response"]
    assert connection.post("/api/v1/assistant/message", json={"session_id":"test",
        "message":f'explain code "{path}"'}).json()["status"] == "blocked"
    assert any(event["tool_id"] == "coding.explain" and event["verified"] for event in
               connection.get("/api/v1/assistant/activity", params={"session_id":"test"}).json()["events"])
