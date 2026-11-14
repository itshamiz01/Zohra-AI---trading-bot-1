"""Local-only text surface for the Node orchestrator and its confirmation gate."""
import asyncio
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal
from fastapi.responses import Response
from zohra.services.productivity.documents import DocumentInput, DocumentError, PdfInspectionInput
from zohra.services.development.source_explain import CodeInspectionInput
from pydantic import ValidationError

from zohra.services.chat.assistant_orchestrator import text_request, confirm_request, node_request
from zohra.services.chat.assistant_store import assistant_store

router = APIRouter(prefix="/api/v1/assistant", tags=["Assistant Orchestrator"])


def local_only(request: Request):
    origin = request.headers.get("origin")
    if request.url.hostname not in {"127.0.0.1", "localhost", "::1"} or (
            origin and (urlsplit(origin).netloc != request.headers.get("host") or urlsplit(origin).scheme != request.url.scheme)):
        raise HTTPException(403, "Assistant actions are available only from this local dashboard.")
    if not request.client or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Remote device control is not paired or authenticated.")


class Message(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    message: str = Field(min_length=1, max_length=4000)


class Confirmation(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    confirmation_id: str = Field(min_length=1, max_length=128)
    decision: bool = Field(strict=True)


@router.post("/message")
async def message(payload: Message, request: Request):
    local_only(request)
    return await text_request(payload.session_id, payload.message)


@router.post("/confirm")
async def confirm(payload: Confirmation, request: Request):
    local_only(request)
    return await confirm_request(payload.session_id, payload.confirmation_id, payload.decision)


@router.get("/history")
async def history(request: Request, session_id: str):
    local_only(request)
    from re import fullmatch
    if not fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(422, "Invalid conversation session")
    records = await asyncio.to_thread(assistant_store.history, session_id, True)
    pending = await asyncio.to_thread(node_request, {"session_id": session_id, "operation": "pending"})
    return {"messages": records, "pending": pending.get("pending")}


@router.get("/capabilities")
async def capabilities(request: Request):
    local_only(request)
    from zohra.services.tool_execution.catalog import capability_inventory
    return {"runtime": "Python FastAPI + existing Node confirmation bridge", "text_confirmation_phase": 1,
        "universal_roadmap_status": "Foundation implemented; remaining modules tracked in the integration matrix", "trading_writes": False,
        "writer_validation": "Awaiting actual manuscript/character-bible sources and live Anthropic validation",
        "voice_upgrade_started": True, "voice_routing": "Shared text classifier and confirmation gate; live STT acceptance pending",
        "anthropic_key_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "anthropic_model_configured": bool(os.getenv("ANTHROPIC_MODEL")),
        "tools": await asyncio.to_thread(capability_inventory),
        "security": {"scope": "Local loopback user session only", "remote_control": False, "strong_authentication": "Not integrated; high-risk tools remain blocked"},
        "actions": ["confirmed file and local PDF/Word/Excel creation", "verified same-session PDF page reading and text search", "local Python source inspection", "confirmed to-dos", "confirmed Notepad/Calculator launch", "confirmed public browser launch", "confirmed grounded Writer reviews (requires configuration)", "read-only backend updates", "public search", "chat", "process monitoring", "network inspection", "confirmed capability controls"]}


class ToolControl(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    tool_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.]+$")
    enabled: bool = Field(strict=True)


class WindowsControl(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    action: Literal["configure_audio", "configure_brightness"]
    args: dict

    @model_validator(mode="after")
    def validate_control(self):
        from zohra.services.automation.windows_controls import AudioChange, BrightnessChange
        model = AudioChange if self.action == "configure_audio" else BrightnessChange
        self.args = model.model_validate(self.args).model_dump()
        return self


@router.get("/windows/status")
async def windows_status(request: Request, session_id: str, kind: Literal["audio", "display"]):
    local_only(request)
    from re import fullmatch
    if not fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(422, "Invalid conversation session")
    from zohra.services.chat.assistant_orchestrator import native_status
    return await native_status(session_id, kind)


@router.post("/windows/control")
async def windows_control(payload: WindowsControl, request: Request):
    local_only(request)
    from zohra.services.chat.assistant_orchestrator import propose_native
    return await propose_native(payload.session_id, payload.action, payload.args)


class DocumentRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    args: DocumentInput


@router.post("/documents")
async def create_document(payload: DocumentRequest, request: Request):
    local_only(request)
    from zohra.services.chat.assistant_orchestrator import propose_document
    return await propose_document(payload.session_id, payload.args.model_dump())


@router.get("/documents")
async def documents(request: Request, session_id: str):
    local_only(request)
    from re import fullmatch
    from zohra.services.productivity.documents import list_documents
    if not fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(422, "Invalid conversation session")
    return {"documents": await asyncio.to_thread(list_documents, session_id)}


@router.get("/pdf/inspect")
async def inspect_verified_pdf(request: Request, session_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,128}$"),
                               filename: str = Query(min_length=1, max_length=120),
                               query: str = Query(default="", max_length=120),
                               page: int | None = Query(default=None, ge=1, le=120)):
    local_only(request)
    try:
        args = PdfInspectionInput(session_id=session_id, filename=filename, query=query, page=page)
    except ValidationError as error:
        raise HTTPException(422, "Invalid PDF inspection request") from error
    from zohra.services.chat.assistant_orchestrator import pdf_inspection_request
    return await pdf_inspection_request(session_id, args.model_dump(exclude={"session_id"}))


@router.get("/code/inspect")
async def inspect_project_code(request: Request, session_id: str = Query(pattern=r"^[A-Za-z0-9_-]{1,128}$"),
                               path: str = Query(min_length=1, max_length=240),
                               symbol: str = Query(default="", max_length=160)):
    local_only(request)
    try:
        args = CodeInspectionInput(path=path, symbol=symbol)
    except ValidationError as error:
        raise HTTPException(422, "Invalid project code inspection request") from error
    from zohra.services.chat.assistant_orchestrator import code_inspection_request
    return await code_inspection_request(session_id, args.model_dump())


@router.get("/documents/{artifact_id}")
async def download_document(artifact_id: str, request: Request, session_id: str):
    local_only(request)
    from re import fullmatch
    from zohra.services.productivity.documents import read_document
    if not fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id) or not fullmatch(r"[a-f0-9-]{36}", artifact_id):
        raise HTTPException(422, "Invalid document or conversation identifier")
    try:
        data, filename, media_type = await asyncio.to_thread(read_document, session_id, artifact_id)
    except DocumentError as error:
        raise HTTPException(404 if error.code == "NOT_FOUND" else 409, str(error)) from error
    except OSError as error:
        raise HTTPException(409, "Document is no longer accessible") from error
    return Response(data, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"',
                    "Cache-Control":"no-store", "X-Content-Type-Options":"nosniff"})


@router.post("/capabilities/control")
async def control_capability(payload: ToolControl, request: Request):
    local_only(request)
    from zohra.services.chat.assistant_orchestrator import text_request
    return await text_request(payload.session_id, f"{'enable' if payload.enabled else 'disable'} tool {payload.tool_id}")


@router.get("/activity")
async def activity(request: Request, session_id: str):
    local_only(request)
    from re import fullmatch
    from zohra.services.tool_execution.state import CapabilityStore
    if not fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise HTTPException(422, "Invalid conversation session")
    return {"events": await asyncio.to_thread(CapabilityStore().history, session_id)}


@router.get("/writer/sources")
async def writer_sources(request: Request):
    local_only(request)
    return await asyncio.to_thread(node_request, {"session_id": "source-inventory", "operation": "writer_sources"})
