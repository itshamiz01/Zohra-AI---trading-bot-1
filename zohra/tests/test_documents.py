"""Real local exports, exact approvals and guarded downloads; no OS or trading writes."""
import asyncio
import io
import json
import time
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zohra.api import assistant_router as api_module
from zohra.services.chat import assistant_orchestrator as orchestrator
from zohra.services.chat.assistant_store import AssistantStore
from zohra.services.productivity.documents import (
    DocumentInput, DocumentError, prepare_document, execute_document, read_document,
    list_documents, workbook_rows, inspect_pdf, PdfInspectionInput, CapabilityStore,
)


def arguments(format="pdf", content="First paragraph.\nSecond paragraph with <tags> & signs."):
    return {"format":format,"filename":"document." + format,"title":"Document Export Check","content":content}


def approved(store, args, *, session="test", status="executing", expires=None):
    id = str(uuid4())
    with store.session() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS confirmations(id TEXT PRIMARY KEY, session TEXT NOT NULL, lane TEXT NOT NULL,
            action TEXT NOT NULL, args TEXT NOT NULL, description TEXT NOT NULL, consequence TEXT NOT NULL,
            status TEXT NOT NULL, expires INTEGER NOT NULL)""")
        db.execute("INSERT INTO confirmations VALUES(?,?,?,?,?,?,?,?,?)",
                   (id,session,"TASK","export_document",json.dumps(args),"Create document","New local file",status,expires or int(time.time()*1000)+300000))
    return {"id":id,"session":session}


@pytest.mark.parametrize("format", ["pdf", "docx", "xlsx"])
def test_real_export_exact_confirmation_and_readback(tmp_path, format):
    store = CapabilityStore(tmp_path)
    args = arguments(format, '[["Item","Value"],["Report",42],["Formula","=1+2"],["Flag",true]]' if format == "xlsx" else "First paragraph.\nSecond paragraph with <tags> & signs.")
    preview = prepare_document(args, store)
    assert preview["args"] == args
    assert not (tmp_path / "files").exists()
    with pytest.raises(DocumentError, match="separate confirmed"):
        execute_document(args, None, store)
    approval = approved(store, args)
    result = execute_document(args, approval, store)
    assert result["verified"] and result["bytes"] > 100
    data, filename, media_type = read_document("test", result["artifact_id"], store)
    assert filename == args["filename"] and len(data) == result["bytes"]
    assert media_type.startswith("application/")
    assert list_documents("other", store) == []
    assert list_documents("test", store)[0]["artifact_id"] == result["artifact_id"]
    with pytest.raises(DocumentError, match="already consumed"):
        execute_document(args, approval, store)
    if format == "xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(io.BytesIO(data), data_only=False)
        assert workbook.active["B3"].value == "=1+2" and workbook.active["B3"].data_type == "s"
        assert workbook.active["B2"].value == 42 and workbook.active["B4"].value is True
        workbook.close()


@pytest.mark.parametrize("change", [
    {"filename":"../escape.pdf"}, {"filename":"NUL.pdf"}, {"filename":"C:\\private.pdf"},
    {"filename":"wrong.xlsx"}, {"content":""}, {"content":"x\x00y"}, {"format":"exe"},
    {"title":True}, {"approval":{"id":"fake"}}, {"content":"x"*100001},
])
def test_strict_bounded_document_input(change):
    with pytest.raises(ValueError):
        DocumentInput.model_validate({**arguments(), **change})


@pytest.mark.parametrize("content", ['[]', '{}', '[["a"],[1,2]]', '[[{}]]', '[[NaN]]', '[[9007199254740993]]', 'a,b\n1', '"unfinished'])
def test_invalid_tables_do_not_create_output(content):
    with pytest.raises(DocumentError):
        workbook_rows(content)


def test_hindi_word_is_preserved_and_pdf_reports_real_limitation(tmp_path):
    from docx import Document
    content = "\u0928\u092e\u0938\u094d\u0924\u0947 \u0939\u092e\u093f\u0926\n\u092f\u0939 \u0938\u0939\u0940 \u092b\u093e\u0907\u0932 \u0939\u0948"
    store = CapabilityStore(tmp_path)
    args = arguments("docx", content)
    result = execute_document(args, approved(store, args), store)
    data, _, _ = read_document("test",result["artifact_id"],store)
    assert Document(io.BytesIO(data)).paragraphs[1].text == content.splitlines()[0]
    with pytest.raises(DocumentError, match="Use Word for Hindi"):
        prepare_document(arguments("pdf",content),store)


@pytest.mark.parametrize("kind", ["wrong_session", "pending", "expired", "modified", "revoked"])
def test_missing_or_modified_authority_cannot_write(tmp_path, kind):
    store = CapabilityStore(tmp_path)
    args = arguments()
    approval = approved(store,args,status="pending" if kind == "pending" else "executing", expires=1 if kind == "expired" else None)
    if kind == "wrong_session":
        approval["session"] = "other"
    if kind == "modified":
        args = {**args,"content":"Changed after approval"}
    if kind == "revoked":
        with store.session() as db:
            db.execute("INSERT INTO tool_controls VALUES('documents.create',0,'now')")
    with pytest.raises(DocumentError):
        execute_document(args,approval,store)
    assert not (tmp_path / "files").exists()


def test_original_files_and_foreign_downloads_are_protected(tmp_path):
    store = CapabilityStore(tmp_path)
    args = arguments()
    result = execute_document(args,approved(store,args),store)
    target = tmp_path / result["path"]
    original = target.read_bytes()
    with pytest.raises(DocumentError,match="already exists"):
        prepare_document(args,store)
    assert target.read_bytes() == original
    with pytest.raises(DocumentError,match="belongs to this conversation"):
        read_document("other",result["artifact_id"],store)
    target.write_bytes(original + b"tampered")
    with pytest.raises(DocumentError,match="changed since creation"):
        read_document("test",result["artifact_id"],store)


def test_links_and_hardlinks_cannot_be_downloaded(tmp_path):
    store = CapabilityStore(tmp_path)
    args = arguments()
    result = execute_document(args,approved(store,args),store)
    target = tmp_path / result["path"]
    alias = tmp_path / "alias.pdf"
    alias.hardlink_to(target)
    with pytest.raises(DocumentError,match="hard links"):
        read_document("test",result["artifact_id"],store)


def test_verified_pdf_pages_search_and_session_isolation(tmp_path):
    store = CapabilityStore(tmp_path)
    args = arguments("pdf", "First page text. The answer is nebula.\n" + "More evidence.\n" * 180)
    result = execute_document(args,approved(store,args),store)
    first = inspect_pdf("test",args["filename"],page=1,store=store)
    assert first["page_count"] > 1 and first["pages"][0]["page"] == 1
    assert "nebula" in first["pages"][0]["text"]
    second = inspect_pdf("test",args["filename"],page=2,store=store)
    assert second["pages"][0]["page"] == 2
    found = inspect_pdf("test",args["filename"],query="NEBULA",store=store)
    assert found["match_count"] == 1 and found["matches"][0]["page"] == 1
    no_match = inspect_pdf("test",args["filename"],query="missing",store=store)
    assert no_match["match_count"] == 0 and no_match["text_available"]
    with pytest.raises(DocumentError,match="belongs to this conversation"):
        inspect_pdf("another",args["filename"],store=store)
    with pytest.raises(DocumentError,match="does not exist"):
        inspect_pdf("test",args["filename"],page=119,store=store)
    with pytest.raises(ValueError):
        PdfInspectionInput(session_id="test",filename="../escape.pdf")
    with pytest.raises(ValueError):
        PdfInspectionInput(session_id="test",filename=args["filename"],query="nebula",page=1)
    (tmp_path/result["path"]).write_bytes(b"changed")
    with pytest.raises(DocumentError,match="changed since creation"):
        inspect_pdf("test",args["filename"],store=store)


def test_pdf_inspection_respects_read_capability_revocation(tmp_path):
    store = CapabilityStore(tmp_path)
    args = arguments()
    execute_document(args,approved(store,args),store)
    with store.session() as db:
        db.execute("INSERT INTO tool_controls VALUES('document.pdf',0,'now')")
    with pytest.raises(DocumentError,match="revoked"):
        inspect_pdf("test",args["filename"],store=store)


def test_pdf_tool_result_does_not_publish_private_text(tmp_path, monkeypatch):
    from zohra.services.tool_execution.catalog import get_registry
    from zohra.services.tool_execution.engine import ToolExecutor
    from zohra.services.tool_execution.models import ToolCall
    from zohra.security.permissions import PermissionTier
    from zohra.services.tool_execution import engine as engine_module
    store = CapabilityStore(tmp_path)
    args = arguments("pdf", "Private nebula manuscript text.")
    execute_document(args,approved(store,args),store)
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE",str(tmp_path))
    events = []
    async def capture(event_type, payload):
        events.append((event_type,payload))
    monkeypatch.setattr(engine_module.event_bus,"publish",capture)
    call = ToolCall("document.pdf","read",{"session_id":"test","filename":args["filename"]},"test",PermissionTier.READ_ONLY,True)
    outcome = asyncio.run(ToolExecutor(get_registry(),store=store).execute(call))
    assert outcome.status == "completed" and "nebula" in outcome.result["pages"][0]["text"]
    assert events[0][1]["result"]["result"] == {"redacted":True}
    assert "nebula" not in json.dumps(events)


@pytest.fixture
def client(tmp_path, monkeypatch):
    root = tmp_path / "runtime"
    monkeypatch.setenv("ZOHRA_ASSISTANT_WORKSPACE",str(root))
    history = AssistantStore(tmp_path / "history.db")
    monkeypatch.setattr(orchestrator,"assistant_store",history)
    monkeypatch.setattr(api_module,"assistant_store",history)
    app = FastAPI()
    @app.middleware("http")
    async def local_transport(request, call_next):
        request.scope["client"] = ("127.0.0.1",50000)
        return await call_next(request)
    app.include_router(api_module.router)
    with TestClient(app,base_url="http://127.0.0.1") as connection:
        yield connection, root


def test_http_preview_confirm_download_reload_and_audit(client):
    connection, root = client
    args = arguments("xlsx","Name,Value\nTest,=SUM(A1:A2)")
    proposal = connection.post("/api/v1/assistant/documents",json={"session_id":"test","args":args}).json()
    assert proposal["status"] == "pending_confirmation"
    assert not (root / "files").exists()
    confirmation = {"session_id":"test","confirmation_id":proposal["pending"]["id"],"decision":True}
    result = connection.post("/api/v1/assistant/confirm",json=confirmation).json()
    assert result["status"] == "success" and result["execution"]["verified"]
    artifact = result["data"]["artifact_id"]
    download = connection.get(f"/api/v1/assistant/documents/{artifact}?session_id=test")
    assert download.status_code == 200 and download.content == (root/result["data"]["path"]).read_bytes()
    assert download.headers["cache-control"] == "no-store"
    assert connection.get(f"/api/v1/assistant/documents/{artifact}?session_id=other").status_code == 404
    assert connection.get(f"/api/v1/assistant/documents/{artifact}?session_id=test",headers={"Origin":"https://evil.example"}).status_code == 403
    assert connection.get("/api/v1/assistant/documents?session_id=test").json()["documents"][0]["artifact_id"] == artifact
    assert connection.post("/api/v1/assistant/confirm",json=confirmation).json()["status"] == "failed"
    event = connection.get("/api/v1/assistant/activity?session_id=test").json()["events"][1]
    assert event["tool_id"] == "documents.create" and event["verified"]


def test_http_pdf_inspection_and_text_command_share_read_tool(client):
    connection, root = client
    args = arguments("pdf","Searchable comet on page one.\nMore source text.")
    proposal = connection.post("/api/v1/assistant/documents",json={"session_id":"test","args":args}).json()
    result = connection.post("/api/v1/assistant/confirm",json={"session_id":"test","confirmation_id":proposal["pending"]["id"],"decision":True}).json()
    assert result["verified"]
    endpoint = "/api/v1/assistant/pdf/inspect"
    response = connection.get(endpoint,params={"session_id":"test","filename":args["filename"]})
    assert response.status_code == 200 and response.json()["verified"]
    assert "Searchable comet" in response.json()["data"]["pages"][0]["text"]
    search = connection.get(endpoint,params={"session_id":"test","filename":args["filename"],"query":"comet"}).json()
    assert search["data"]["match_count"] == 1 and search["data"]["matches"][0]["page"] == 1
    assert connection.get(endpoint,params={"session_id":"test","filename":args["filename"],"query":"x","page":1}).status_code == 422
    assert connection.get(endpoint,params={"session_id":"test","filename":args["filename"]},headers={"Origin":"https://evil.example"}).status_code == 403
    foreign = connection.get(endpoint,params={"session_id":"foreign","filename":args["filename"]}).json()
    assert foreign["status"] == "failed" and "belongs to this conversation" in foreign["response"]
    typed = connection.post("/api/v1/assistant/message",json={"session_id":"test","message":'search PDF "document.pdf" for comet'}).json()
    assert typed["status"] == "success" and typed["data"]["match_count"] == 1
    async def collect():
        return [event async for event in orchestrator.voice_events("test",'read PDF "document.pdf" page 1')]
    spoken = asyncio.run(collect())
    answer = next(event["result"] for event in spoken if event["type"] == "assistant_result")
    assert answer["verified"] and answer["data"]["pages"][0]["page"] == 1
    assert any(event["tool_id"] == "document.pdf" and event["verified"] for event in connection.get("/api/v1/assistant/activity?session_id=test").json()["events"])


def test_text_and_voice_use_exact_same_document_gate(client):
    connection, root = client
    text = 'create PDF "typed.pdf" with This is approved text, not a trading command.'
    proposal = connection.post("/api/v1/assistant/message",json={"session_id":"typed","message":text}).json()
    assert proposal["status"] == "pending_confirmation"
    assert connection.post("/api/v1/assistant/message",json={"session_id":"typed","message":"confirm"}).json()["verified"]
    async def collect(session,text):
        return [event async for event in orchestrator.voice_events(session,text)]
    events = asyncio.run(collect("voice",'create Word "spoken.docx" with Voice surface uses the shared router.'))
    pending = next(event["result"] for event in events if event["type"] == "assistant_result")
    assert pending["status"] == "pending_confirmation"
    assert not (root / "files/documents/spoken.docx").exists()
    events = asyncio.run(collect("voice","confirm"))
    result = next(event["result"] for event in events if event["type"] == "assistant_result")
    assert result["verified"] and (root/result["data"]["path"]).is_file()


def test_http_rejects_extra_authority_and_cancellation_creates_nothing(client):
    connection, root = client
    args = arguments()
    assert connection.post("/api/v1/assistant/documents",json={"session_id":"test","args":args,"confirmed":True}).status_code == 422
    assert connection.post("/api/v1/assistant/documents",json={"session_id":"test","args":{**args,"filename":"../escape.pdf"}}).status_code == 422
    proposal = connection.post("/api/v1/assistant/documents",json={"session_id":"test","args":args}).json()
    result = connection.post("/api/v1/assistant/confirm",json={"session_id":"test","confirmation_id":proposal["pending"]["id"],"decision":False}).json()
    assert result["status"] == "cancelled" and not (root / "files").exists()


def test_registry_document_tool_only_previews(client):
    from zohra.services.tool_execution.catalog import get_registry
    from zohra.services.tool_execution.engine import ToolExecutor, PermissionPolicy
    from zohra.services.tool_execution.models import ToolCall
    from zohra.security.permissions import PermissionTier
    connection, root = client
    definition = get_registry().definition("documents.create")
    assert definition.confirmation_required and definition.confirmation_bridge
    result = asyncio.run(ToolExecutor(get_registry(),PermissionPolicy({"documents":3})).execute(ToolCall("documents.create","preview",arguments(),"test",PermissionTier.READ_ONLY,True)))
    assert result.status == "requires_confirmation" and not (root / "files").exists()
