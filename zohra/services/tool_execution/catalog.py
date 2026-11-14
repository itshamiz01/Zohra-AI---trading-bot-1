"""Adapters around working Zohra services; future capabilities are not executable stubs."""
import importlib.util
import json
import os
import platform
import shutil
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from zohra.services.tool_execution.registry import CapabilityState, ToolDefinition, ToolRegistry, EmptyInput
from zohra.services.tool_execution.state import PROJECT, CapabilityStore
from zohra.services.automation.windows_controls import AudioChange, BrightnessChange, audio_status, display_status, native_dependencies, native_control_availability
from zohra.services.productivity.documents import DocumentInput, PdfInspectionInput, DEPENDENCIES, inspect_pdf
from zohra.services.development.source_explain import CodeInspectionInput, inspect_code


TOOL_IDS = json.loads((PROJECT / "assistant_runtime" / "tool-ids.json").read_text(encoding="utf-8"))
ACTION_TO_TOOL = TOOL_IDS["actions"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchInput(Input):
    query: str = Field(min_length=1, max_length=400)
    kind: Literal["web", "news"] = "web"
    recency: Literal["d", "w", "m", "y"] | None = None
    max_results: int = Field(default=5, ge=1, le=5)


class BackendInput(Input):
    query: str = Field(default="", max_length=200)


class FileInput(Input):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=100000)


class TaskInput(Input):
    title: str = Field(min_length=1, max_length=500)


class CompleteInput(Input):
    task_id: int = Field(ge=1)


class AppInput(Input):
    app: Literal["notepad", "calculator"]


class BrowserInput(Input):
    url: str = Field(min_length=1, max_length=2000)


class WriterInput(Input):
    text: str = Field(min_length=1, max_length=4000)


class ControlInput(Input):
    tool_id: str = Field(min_length=1, max_length=100)
    enabled: bool


class SnapshotOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: str
    observed_at: str


class ProcessOutput(SnapshotOutput):
    process_count: int
    processes: list[dict]
    cpu_usage_pct: float
    ram_usage_pct: float


class NetworkOutput(SnapshotOutput):
    interfaces: list[dict]


class AudioOutput(SnapshotOutput):
    device_id: str
    device_name: str
    volume: float
    muted: bool


class DisplayOutput(SnapshotOutput):
    monitors: list[dict]


class ProposalOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: Literal["pending_confirmation"]
    response: str
    pending: dict


class TaskOutput(BaseModel):
    tasks: list[dict]


class SearchOutput(BaseModel):
    model_config = ConfigDict(extra="allow")
    results: list[dict]
    retrieved_at: str


class PdfInspectionOutput(SnapshotOutput):
    filename: str
    page_count: int
    displayed_pages: int
    pages: list[dict]
    matches: list[dict]
    match_count: int


class CodeInspectionOutput(SnapshotOutput):
    path: str
    symbol: str
    kind: Literal["module", "class", "function"]
    summary: str
    references: list[dict]
    sha256: str
    static_only: bool


def dependency(*modules):
    missing = [name for name in modules if importlib.util.find_spec(name) is None]
    return (CapabilityState.DEPENDENCY_MISSING, "Missing: " + ", ".join(missing)) if missing else (CapabilityState.AVAILABLE, "Ready")


def node_available(windows=False):
    if windows and platform.system() != "Windows":
        return CapabilityState.UNSUPPORTED, "Requires a native Windows user session"
    binary = os.getenv("ZOHRA_NODE_BINARY", "node")
    if shutil.which(binary) is None:
        return CapabilityState.DEPENDENCY_MISSING, "Node.js 24 or newer is required"
    return CapabilityState.AVAILABLE, "Uses the existing Node confirmation bridge"


def writer_available():
    state, reason = node_available()
    if state != CapabilityState.AVAILABLE:
        return state, reason
    if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("ANTHROPIC_MODEL"):
        return CapabilityState.DEPENDENCY_MISSING, "Anthropic API key/model and approved manuscript sources are required"
    return state, "Private source upload requires separate confirmation; live grounding acceptance is pending"


def processes():
    import psutil
    rows, inaccessible = [], 0
    for process in psutil.process_iter(["pid", "name", "memory_info", "cpu_times", "status"]):
        try:
            item = process.info
            rows.append({"pid": item["pid"], "name": item["name"],
                "memory_bytes": item["memory_info"].rss if item["memory_info"] else None,
                "cpu_time_seconds": sum(item["cpu_times"][:2]) if item["cpu_times"] else None,
                "status": item["status"]})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            inaccessible += 1
    rows.sort(key=lambda item: item["memory_bytes"] or 0, reverse=True)
    return {"source": "native psutil process snapshot", "observed_at": datetime.now(timezone.utc).isoformat(),
        "process_count": len(rows), "inaccessible_count": inaccessible, "processes": rows[:40],
        "ram_usage_pct": psutil.virtual_memory().percent, "cpu_usage_pct": psutil.cpu_percent(interval=0.1),
        "uptime_seconds": max(0, datetime.now(timezone.utc).timestamp() - psutil.boot_time()),
        "limitations": "CPU percent is a 100ms system sample. Per-process CPU is cumulative time, not instantaneous usage. No process was closed."}


def network():
    import psutil
    states = psutil.net_if_stats()
    counters = psutil.net_io_counters(pernic=True)
    interfaces = []
    for name, addresses in psutil.net_if_addrs().items():
        state, totals = states.get(name), counters.get(name)
        interfaces.append({"name": name, "up": state.isup if state else None,
            "link_speed_mbps": state.speed if state else None,
            "addresses": [{"family": str(item.family), "address": item.address, "netmask": item.netmask} for item in addresses],
            "bytes_sent": totals.bytes_sent if totals else None, "bytes_received": totals.bytes_recv if totals else None})
    return {"source": "native psutil interface snapshot", "observed_at": datetime.now(timezone.utc).isoformat(),
        "interfaces": interfaces, "limitations": "Link speed and cumulative counters are not an internet speed test. Public IP, Wi-Fi scanning and connection changes are not performed."}


def verify_snapshot(result):
    return isinstance(result, dict) and bool(result.get("source")) and bool(result.get("observed_at")) and not result.get("error")


def bridge_proposal(action, **params):
    from zohra.services.chat.assistant_orchestrator import node_request
    # Generic tool execution never receives a user's confirmation credential.
    return node_request({"session_id": "tool-preview", "operation": "propose", "action": action, "args": params})


@lru_cache(maxsize=1)
def get_registry():
    registry = ToolRegistry()
    def add(name, description, category, handler=None, **kwargs):
        registry.register(name, handler, definition=ToolDefinition(name, description, category, **kwargs))

    add("capabilities.list", "Inspect actual tool availability and permissions", "Security",
        lambda: {"tools": capability_inventory()}, verification=lambda result: isinstance(result.get("tools"), list))
    add("system.processes", "Read CPU, RAM, uptime and the largest processes by memory", "Windows", processes,
        output_model=ProcessOutput, dependencies=("psutil",), permissions=("system.read",), availability=lambda: dependency("psutil"), verification=verify_snapshot)
    add("system.network", "Read local interfaces, addresses and cumulative traffic counters", "Windows", network,
        output_model=NetworkOutput, dependencies=("psutil",), permissions=("network.read",), availability=lambda: dependency("psutil"), verification=verify_snapshot)
    add("system.audio", "Read current master volume, mute and default output identity", "Windows", audio_status,
        platform="Windows", output_model=AudioOutput, dependencies=("pycaw", "comtypes"), permissions=("audio.read",),
        availability=lambda: native_dependencies("audio"), verification=verify_snapshot)
    add("system.display", "Read active WMI monitors and actual brightness", "Windows", display_status,
        platform="Windows", output_model=DisplayOutput, dependencies=("pywin32",), permissions=("display.read",),
        availability=lambda: native_dependencies("display"), verification=verify_snapshot)
    for action, name, model, description, kind in (
        ("configure_audio", "windows.audio", AudioChange, "Set master volume or mute after exact device-bound confirmation and read-back", "audio"),
        ("configure_brightness", "windows.display", BrightnessChange, "Set WMI-compatible monitor brightness after exact confirmation and read-back", "display"),
    ):
        add(name, description, "Windows", lambda action=action, **params: bridge_proposal(action, **params),
            platform="Windows", input_model=model, output_model=ProposalOutput, risk_level=1,
            confirmation_required=True, confirmation_bridge=True, timeout_sec=45, permissions=(name,),
            dependencies=("Node.js >=24", "native Python Windows session"),
            availability=lambda kind=kind: native_control_availability(kind))
    from zohra.services.chat.assistant_tools import get_backend_update
    for domain in ("system", "trading", "research", "memory", "learning", "agents"):
        add("backend." + domain, "Read the existing " + domain + " dashboard snapshot; never execute trades", "Backend",
            lambda query="", domain=domain: get_backend_update(domain, query), input_model=BackendInput,
            output_model=SnapshotOutput, permissions=(domain + ".read",), verification=verify_snapshot)
    from zohra.services.chat.assistant_search import search_web
    add("web.search", "Search public snippets with actual source links; not full-page verification", "Research", search_web,
        input_model=SearchInput, output_model=SearchOutput, timeout_sec=30, dependencies=("ddgs",), permissions=("public_web.read",),
        availability=lambda: dependency("ddgs"), verification=lambda result: bool(result.get("retrieved_at")) and isinstance(result.get("results"), list))
    def task_list():
        from zohra.services.chat.assistant_orchestrator import node_request
        return node_request({"session_id": "registry-task-list", "operation": "tasks"})
    add("tasks.list", "Read saved assistant to-dos; these are not scheduled jobs", "Productivity", task_list,
        output_model=TaskOutput, availability=node_available, verification=lambda result: isinstance(result.get("tasks"), list))
    # CHAT and WRITING retain their existing provider adapters; no new paid provider is introduced.
    add("chat.respond", "Conversation using the already-configured assistant provider", "Conversation",
        availability=lambda: (CapabilityState.AVAILABLE, "Existing configured provider; service health is checked on use"))
    for action, name, model, description, category, risk in (
        ("write_file", "files.create", FileInput, "Create a new .txt/.md file inside assistant_workspace/files, never overwrite", "Files", 2),
        ("create_task", "tasks.create", TaskInput, "Save a to-do item; does not execute or schedule it", "Productivity", 1),
        ("complete_task", "tasks.complete", CompleteInput, "Mark an existing to-do complete", "Productivity", 1),
        ("launch_app", "windows.launch", AppInput, "Launch only Notepad or Calculator in the Windows session", "Windows", 1),
        ("open_browser", "browser.open", BrowserInput, "Dispatch a public HTTP(S) URL to the default browser; no form submission", "Web", 1),
        ("set_tool_enabled", "security.configure", ControlInput, "Confirm enabling or revoking an existing assistant capability", "Security", 2),
    ):
        add(name, description, category, lambda action=action, **params: bridge_proposal(action, **params), input_model=model,
            risk_level=risk, confirmation_required=True, confirmation_bridge=True, timeout_sec=45,
            output_model=ProposalOutput,
            permissions=(name,), availability=lambda action=action: node_available(action in {"launch_app", "open_browser"}),
            dependencies=("Node.js >=24",), platform="Windows" if action in {"launch_app", "open_browser"} else "Shared")
    add("writer.review", "Source-grounded line editing, developmental feedback, continuity checks and drafting", "Writing",
        input_model=WriterInput, risk_level=2, confirmation_required=True, timeout_sec=45,
        permissions=("private_sources.upload",), dependencies=("Anthropic key/model", "approved manuscript and character bible"), availability=writer_available)
    def document_available():
        state, reason = node_available()
        if state != CapabilityState.AVAILABLE:
            return state, reason
        return dependency(*{module for modules in DEPENDENCIES.values() for module in modules})
    add("documents.create", "Create and verify a new local PDF, Word or Excel document from supplied content; no overwrite or upload", "Productivity",
        lambda **params: bridge_proposal("export_document", **params), input_model=DocumentInput, output_model=ProposalOutput,
        risk_level=2, confirmation_required=True, confirmation_bridge=True, timeout_sec=45, permissions=("documents.create",),
        dependencies=("Node.js >=24", "reportlab", "pypdf", "python-docx", "openpyxl"), availability=document_available)
    add("document.pdf", "Read pages or search text in a verified PDF created in this conversation; local only, no OCR or cloud upload", "Productivity",
        inspect_pdf, input_model=PdfInspectionInput, output_model=PdfInspectionOutput, permissions=("documents.read",),
        dependencies=("pypdf",), availability=lambda: dependency("pypdf"), timeout_sec=20, private_output=True,
        verification=lambda result: result.get("source") == "verified local assistant PDF" and
            isinstance(result.get("pages"), list) and isinstance(result.get("matches"), list) and
            result.get("page_count", 0) >= 1)
    add("coding.explain", "Inspect a project Python module, class or function with source line references; static and local only", "Development",
        inspect_code, input_model=CodeInspectionInput, output_model=CodeInspectionOutput,
        permissions=("project_source.read",), timeout_sec=15, private_output=True,
        verification=lambda result: result.get("source") == "local Python AST" and
            result.get("static_only") is True and len(result.get("sha256", "")) == 64 and
            bool(result.get("summary")) and isinstance(result.get("references"), list))
    # These contracts intentionally have no executable handler. The matrix records their actual blockers.
    for name, category, reason in (
        ("vault.manage", "Security", "No authenticated AES-GCM/Argon2id vault implementation"),
        ("windows.power", "Windows", "Cancelable countdown and strong authenticated approval are not integrated"),
        ("windows.defender", "Windows", "Defender dispatch exists; verified scan/status pipeline is not integrated"),
        ("automation.schedule", "Automation", "Existing scheduler is in-memory; persistent authorized jobs are not integrated"),
        ("windows.terminate", "Windows", "Only monitoring is enabled; PID identity and unsaved-work approval are not integrated"),
        ("network.manage", "Windows", "Wi-Fi writes and measured speed/latency adapters are not integrated"),
        ("security.voice", "Security", "Speaker extractor/liveness/second-factor enrollment unavailable"),
        ("storage.clean", "Windows", "Legacy cleaner reports fixed savings; no verified deletion preview"),
        ("vision.screen", "Vision", "Existing capture/OCR requires consent and central execution integration"),
        ("vision.camera", "Vision", "Existing OpenCV camera requires authorized device and central tool integration"),
        ("vision.screenshot", "Vision", "Capture exists; private file creation is not yet integrated into this gate"),
        ("media.spotify", "Media", "No Spotify OAuth account/provider configured"),
        ("windows.wallpaper", "Windows", "Legacy wallpaper handler is simulated"),
        ("desktop.input", "Windows", "Verified semantic targets and interruption/authorization are not integrated"),
        ("media.youtube", "Media", "Learning parser exists; authorized playback/transcript tools are not integrated"),
        ("desktop.scroll", "Windows", "Intended-window verification is not integrated"),
        ("research.report", "Productivity", "Search exists; sourced synthesis and verified multi-format export are not integrated"),
        ("web.extract", "Research", "Public structured extraction and restrictions pipeline are not integrated"),
        ("website.build", "Development", "No isolated generated-project builder and preview verifier"),
        ("image.generate", "Vision", "No authorized generation provider/model configured"),
        ("document.excel", "Productivity", "Workbook backup, mutation approval and verification are not integrated"),
        ("email.manage", "Productivity", "Existing email module needs configured account and draft/send permission separation"),
        ("whatsapp.manage", "Productivity", "No authorized official account or user-mediated adapter configured"),
        ("document.convert", "Productivity", "Format-specific conversion engines and fidelity verification are not integrated"),
        ("coding.patch", "Development", "No isolated approved-patch/checkpoint/rollback tool"),
        ("coding.vscode", "Development", "No supported VS Code diagnostics/CLI adapter integrated"),
        ("coding.run", "Development", "No constrained generated-script execution environment"),
        ("coding.test", "Development", "No scoped test-generation/execution adapter integrated"),
        ("coding.preferences", "Development", "Workspace-isolated developer preferences are not integrated"),
        ("forms.fill", "Intelligence", "No authorized field-preview/verified-fill workflow"),
        ("shopping.compare", "Intelligence", "Search exists; timestamped merchant comparison/tracking is not integrated"),
        ("video.summarize", "Intelligence", "No authorized incremental transcript/frame pipeline"),
        ("market.information", "Intelligence", "Existing trading snapshots available separately; broader timestamped data providers not integrated"),
        ("choice.resolve", "Intelligence", "Routing clarification exists; persisted workflow choices are not integrated"),
        ("briefing.daily", "Intelligence", "No authorized calendar/email/weather briefing composition"),
        ("workflow.manage", "Automation", "Existing DAG execution lacks persistent cancel/resume and uniform authorization"),
        ("devices.pair", "Devices", "No authenticated device identities, pairing or encrypted remote transport"),
        ("devices.transfer", "Devices", "No authorized receipt-verified cross-device transfer"),
        ("android.agent", "Android", "No Kotlin application/toolchain/device validation in this checkout"),
        ("trading.write", "Trading", "Trading writes intentionally blocked; engine and risk files are not modified"),
    ):
        read_only = name in {"vision.screen", "vision.camera", "network.manage", "document.pdf", "coding.explain", "shopping.compare", "video.summarize", "market.information", "choice.resolve", "briefing.daily"}
        add(name, reason, category, risk_level=0 if read_only else 3, confirmation_required=not read_only,
            reversible=read_only, permissions=(name,), availability=lambda reason=reason: (CapabilityState.UNSUPPORTED, reason))
    return registry


def capability_inventory():
    store = CapabilityStore()
    controls = store.controls()
    last_executions = store.latest()
    records = get_registry().describe()
    for record in records:
        record["enabled"] = controls.get(record["name"], True)
        record["controllable"] = record["name"] in set(ACTION_TO_TOOL.values()) | set(TOOL_IDS["read_tools"]) and record["name"] not in TOOL_IDS["protected"]
        record["last_execution"] = last_executions.get(record["name"])
        record["current_status"] = "Execution Failed" if record["last_execution"] and record["last_execution"]["status"] in {"failed", "blocked", "rejected"} else record["availability"]
        if not record["enabled"]:
            record["availability"] = CapabilityState.PERMISSION_REQUIRED.value
            record["reason"] = "Disabled by owner; pending actions cannot bypass revocation"
    return records


def check_capability(tool_id):
    definition = get_registry().definition(tool_id)
    if definition is None:
        raise PermissionError("UNVERIFIED_TOOL: No validated capability contract")
    if not CapabilityStore().enabled(tool_id):
        raise PermissionError("TOOL_DISABLED: Owner revoked " + tool_id)
    state, reason = definition.availability()
    if state != CapabilityState.AVAILABLE:
        raise PermissionError(f"TOOL_UNAVAILABLE: {state.value}: {reason}")
    return definition
