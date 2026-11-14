"""Node confirmation/routing adapter; never imports a trading executor."""
import asyncio
import json
import logging
import os
import subprocess
import re
import time
import sys
from weakref import WeakValueDictionary
from pathlib import Path

from zohra.services.chat.assistant_tools import execute_tool, redact_data, redact_secrets
from zohra.services.chat.assistant_store import assistant_store

logger = logging.getLogger("zohra.assistant.orchestrator")
PROJECT = Path(__file__).resolve().parents[3]
RUNTIME = PROJECT / "assistant_runtime" / "cli.mjs"
CORE_PROMPT = (RUNTIME.parent / "core-prompt.txt").read_text(encoding="utf-8")
SESSION_LOCKS = WeakValueDictionary()


def route_tool(route):
    from zohra.services.tool_execution.catalog import ACTION_TO_TOOL
    action = route.get("action")
    return ACTION_TO_TOOL.get(action) or {
        "chat": "chat.respond", "search": "web.search", "list_tasks": "tasks.list",
        "writer": "writer.review", "capability_inventory": "capabilities.list",
        "process_status": "system.processes", "network_status": "system.network",
        "audio_status": "system.audio", "display_status": "system.display", "pdf_inspect": "document.pdf",
        "code_inspect": "coding.explain",
    }.get(action) or ("backend." + route["domain"] if action == "backend_update" else None)


def record_execution(session, tool_id, result, started):
    from zohra.services.tool_execution.state import CapabilityStore
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    data = result.get("data")
    verified = result.get("verified") is True or (isinstance(data, dict) and data.get("verified") is True)
    CapabilityStore().record(session, tool_id or "routing", result.get("status", "failed"), elapsed_ms, result.get("error"), verified)
    result["execution"] = {"tool_id": tool_id, "elapsed_ms": elapsed_ms, "verified": verified}
    return result


def capability_failure(error, lane="TASK"):
    return {"lane": lane, "status": "blocked", "response": redact_secrets(f"{lane}: {error}"),
            "error": {"code": "PERMISSION_DENIED", "message": redact_secrets(str(error))}}


async def registry_read(session, tool_id, params=None):
    from zohra.services.tool_execution.catalog import get_registry, check_capability
    from zohra.services.tool_execution.engine import ToolExecutor
    from zohra.services.tool_execution.models import ToolCall
    from zohra.security.permissions import PermissionTier
    try:
        await asyncio.to_thread(check_capability, tool_id)
    except (PermissionError, KeyError) as error:
        return capability_failure(error)
    call = ToolCall(tool_id, "read", params or {}, session, PermissionTier.READ_ONLY, True)
    result = await ToolExecutor(get_registry()).execute(call)
    if result.status != "completed":
        return {"lane": "TASK", "status": "failed", "response": "TASK: " + (result.error or "Tool failed"),
                "error": {"code": result.error_code, "message": result.error}}
    data = redact_data(result.result)
    if tool_id == "capabilities.list":
        available = [row["name"] for row in data["tools"] if row["availability"] == "Available"]
        response = "TASK: Available capabilities: " + ", ".join(available) + ". Unavailable tools are listed with their blockers."
    elif tool_id == "system.processes":
        response = f"TASK: CPU {data['cpu_usage_pct']}%, RAM {data['ram_usage_pct']}%. Read {data['process_count']} processes. No applications were closed."
    elif tool_id == "system.network":
        response = f"TASK: Read {len(data['interfaces'])} network interfaces. No connection was changed."
    elif tool_id == "system.audio":
        response = f"TASK: Master volume {data['volume']}%, {'muted' if data['muted'] else 'unmuted'}, on {data['device_name']}. No setting was changed."
    elif tool_id == "document.pdf":
        if data["query"]:
            snippets = "; ".join(f"page {item['page']}: {item['snippet'][:140]}" for item in data["matches"][:3])
            response = f"TASK: Found {data['match_count']} matches for {data['query']!r} in {data['filename']}. " + (snippets or "No matches.")
        else:
            first = data["pages"][0]
            excerpt = first["text"][:650].strip()
            response = (f"TASK: {data['filename']} has {data['page_count']} pages. Page {first['page']}: " +
                        (excerpt or "No selectable text; this may be a scanned page.") +
                        (" More text is available on screen." if first["characters"] > 650 else ""))
    elif tool_id == "coding.explain":
        response = "TASK: " + data["summary"][:900] + " This is static source inspection; no code was run."
    else:
        response = "TASK: " + "; ".join(f"{item['monitor_id']}: brightness {item['brightness']}%" for item in data['monitors']) + ". No setting was changed."
    return {"lane": "TASK", "status": "success", "response": response, "data": data, "verified": True}


async def pdf_inspection_request(session, args):
    started = time.perf_counter()
    result = await registry_read(session, "document.pdf", {"session_id":session, **args})
    return record_execution(session, "document.pdf", result, started)


async def code_inspection_request(session, args):
    started = time.perf_counter()
    result = await registry_read(session, "coding.explain", args)
    return record_execution(session, "coding.explain", result, started)


async def native_status(session, kind):
    started = time.perf_counter()
    tool_id = "system.audio" if kind == "audio" else "system.display"
    result = await registry_read(session, tool_id)
    return record_execution(session, tool_id, result, started)


async def propose_native(session, action, args):
    from zohra.services.automation.windows_controls import AudioChange, BrightnessChange
    from zohra.services.tool_execution.catalog import check_capability, ACTION_TO_TOOL
    async with session_lock(session):
        started = time.perf_counter()
        model = AudioChange if action == "configure_audio" else BrightnessChange
        validated = model.model_validate(args).model_dump()
        tool_id = ACTION_TO_TOOL[action]
        try:
            await asyncio.to_thread(check_capability, tool_id)
            result = await asyncio.to_thread(node_request, {"session_id":session, "operation":"propose", "action":action, "args":validated})
        except (PermissionError, KeyError, ValueError, OSError) as error:
            await asyncio.to_thread(node_request, {"session_id":session, "operation":"invalidate"})
            result = capability_failure(error)
        record_execution(session, tool_id, result, started)
        await asyncio.to_thread(assistant_store.add_message, session, "user", "Request Windows control: " + json.dumps(validated), None, True)
        await asyncio.to_thread(assistant_store.add_message, session, "assistant", result.get("response", "Request rejected."), None, True)
        return result


async def propose_document(session, args):
    from zohra.services.productivity.documents import DocumentInput
    from zohra.services.tool_execution.catalog import check_capability
    async with session_lock(session):
        started = time.perf_counter()
        validated = DocumentInput.model_validate(args).model_dump()
        try:
            await asyncio.to_thread(check_capability, "documents.create")
            result = await asyncio.to_thread(node_request, {"session_id":session, "operation":"propose", "action":"export_document", "args":validated})
        except (PermissionError, KeyError, ValueError, OSError) as error:
            await asyncio.to_thread(node_request, {"session_id":session, "operation":"invalidate"})
            result = capability_failure(error)
        record_execution(session, "documents.create", result, started)
        await asyncio.to_thread(assistant_store.add_message, session, "user", f"Create {validated['format'].upper()} document {validated['filename']}", None, True)
        await asyncio.to_thread(assistant_store.add_message, session, "assistant", result.get("response", "Request rejected."), None, True)
        return result


async def voice_events(session, transcript):
    from zohra.services.chat.assistant_brain import assistant_brain
    async for event in assistant_brain.run_reasoning_loop(session, transcript):
        yield event


def session_lock(session):
    lock = SESSION_LOCKS.get(session)
    if lock is None:
        lock = SESSION_LOCKS[session] = asyncio.Lock()
    return lock


def node_request(payload):
    try:
        result = subprocess.run([os.getenv("ZOHRA_NODE_BINARY", "node"), str(RUNTIME)],
            input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8",
            capture_output=True, timeout=45, cwd=PROJECT, env={**os.environ,
                "ZOHRA_PYTHON_BINARY": os.getenv("ZOHRA_PYTHON_BINARY", sys.executable)})
        if not result.stdout:
            raise RuntimeError(redact_secrets(result.stderr.strip() or f"Node exited with code {result.returncode}"))
        response = redact_data(json.loads(result.stdout))
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        response = {"lane": "TASK", "status": "failed", "response": redact_secrets(f"TASK: {type(error).__name__}: {error}"),
                    "error": {"code": type(error).__name__, "message": redact_secrets(str(error))}}
    if response.get("error"):
        logger.warning("Assistant action failed: %s", json.dumps(redact_data(response["error"])))
    return response


async def readonly_reply(session, text, route):
    from zohra.services.chat.assistant_brain import assistant_brain
    lane = route["lane"]
    tools = {"get_backend_update", "search_web"} if lane == "TASK" else {"get_backend_update"} if lane == "TRADING" else set()
    instruction = CORE_PROMPT + f"\nThe server-assigned lane for this turn is {lane}. Only read-only tools are available."
    observation = None
    if route["action"] == "pdf_inspect":
        return await registry_read(session, "document.pdf", {"session_id":session, **route["args"]})
    if route["action"] == "code_inspect":
        return await registry_read(session, "coding.explain", route["args"])
    if route["action"] in {"capability_inventory", "process_status", "network_status", "audio_status", "display_status"}:
        return await registry_read(session, route_tool(route))
    if route["action"] == "backend_update":
        observation = await asyncio.to_thread(execute_tool, "get_backend_update", {"domain": route["domain"]})
        # Account and private dashboard observations never go to an external LLM.
        error = observation.get("error")
        data = observation.get("data") or {}
        fields = [f"{key.replace('_', ' ')}: {data[key] if data[key] is not None else 'unavailable'}" for key in
                  ("status", "telemetry_status", "balance", "equity", "daily_pnl", "open_positions", "cpu_usage_pct", "ram_usage_pct", "total_memories")
                  if key in data]
        prefix = "Risk-control health is unverified here; trading writes are disabled. " if lane == "TRADING" else ""
        reply = str(error) if error else "Available backend snapshot. " + ("; ".join(fields) + ". " if fields else "") + f"Observed at {observation.get('observed_at', 'unknown')}."
        return {"lane": lane, "status": "failed" if error else "success", "response": f"{lane}: {prefix}{reply}",
                "data": observation, **({"error": {"message": error}} if error else {})}
    elif route["action"] == "search":
        observation = await asyncio.to_thread(execute_tool, "search_web", {"query": text[:400]})
        tools = set()
    events = [event async for event in assistant_brain.run_reasoning_loop(
        session, text, allowed_tools=tools, system_instruction=instruction,
        allowed_domains={"trading"} if lane == "TRADING" else {"system", "research", "memory", "learning", "agents"}, observation=observation, persist=False)]
    reply = "".join(event["content"] for event in events if event["type"] == "token")
    sources = next((event["sources"] for event in events if event["type"] == "sources"), [])
    if route["action"] == "search" and observation:
        sources = [{**{key: row.get(key) for key in ("title", "url", "publisher", "published_at")},
                    "retrieved_at": observation.get("retrieved_at")} for row in observation.get("results", [])]
    error = next((event["content"] for event in events if event["type"] == "error"), None)
    if observation and observation.get("error"):
        error = observation["error"]
        reply = str(error)
    if lane == "TRADING":
        reply = "Risk-control health is unverified here; trading writes are disabled. " + reply
    elif route["action"] == "search" and not error:
        reply = "Based on search excerpts, not full-page verification: " + reply
    return {"lane": lane, "status": "failed" if error else "success",
            "response": reply if reply.startswith(lane + ":") else f"{lane}: {reply}",
            "sources": sources, **({"data": observation} if observation else {}),
            **({"error": {"message": error}} if error else {})}


async def text_request(session, text):
    async with session_lock(session):
        started = time.perf_counter()
        from zohra.services.tool_execution.catalog import check_capability
        route = await asyncio.to_thread(node_request, {"session_id": session, "operation": "classify", "text": text})
        tool_id = route_tool(route)
        confirmation = re.fullmatch(r"confirm|yes|haan|\u0939\u093e\u0901|cancel|no|nahi", text.strip(), re.I)
        if confirmation:
            pending = (await asyncio.to_thread(node_request, {"session_id":session, "operation":"pending"})).get("pending")
            tool_id = pending.get("tool_id") if pending else None
        try:
            if tool_id and not (confirmation and text.strip().lower() in {"cancel", "no", "nahi"}):
                # Writer configuration errors retain their existing source-aware response.
                if tool_id == "writer.review":
                    from zohra.services.tool_execution.state import CapabilityStore
                    if not CapabilityStore().enabled(tool_id):
                        raise PermissionError("TOOL_DISABLED: Owner revoked writer.review")
                else:
                    await asyncio.to_thread(check_capability, tool_id)
            result = await asyncio.to_thread(node_request, {"session_id": session, "text": text})
        except (PermissionError, KeyError, ValueError, OSError) as error:
            if not confirmation:
                await asyncio.to_thread(node_request, {"session_id":session, "operation":"invalidate"})
            result = capability_failure(error, route.get("lane") or "TASK")
        private_context = result.get("action") not in {"chat", "search"}
        if result.get("status") == "routed":
            action = result["action"]
            result = await readonly_reply(session, text, result)
            await asyncio.to_thread(node_request, {"session_id": session, "operation": "report", "lane": result["lane"],
                "action": action, "status": result["status"], "error": result.get("error")})
        record_execution(session, tool_id, result, started)
        await asyncio.to_thread(assistant_store.add_message, session, "user", redact_secrets(text), None, private_context)
        await asyncio.to_thread(assistant_store.add_message, session, "assistant", result.get("response", "Request rejected."), result.get("sources"), private_context)
        return result


async def confirm_request(session, confirmation_id, decision):
    async with session_lock(session):
        started = time.perf_counter()
        from zohra.services.tool_execution.catalog import check_capability
        pending = (await asyncio.to_thread(node_request, {"session_id":session, "operation":"pending"})).get("pending")
        tool_id = pending.get("tool_id") if pending else None
        try:
            if decision and pending and pending["id"] == confirmation_id:
                await asyncio.to_thread(check_capability, tool_id)
            result = await asyncio.to_thread(node_request, {"session_id": session, "operation": "confirm",
                "confirmation_id": confirmation_id, "decision": decision})
        except (PermissionError, KeyError, ValueError, OSError) as error:
            result = capability_failure(error)
        record_execution(session, tool_id, result, started)
        await asyncio.to_thread(assistant_store.add_message, session, "user", "Confirm" if decision else "Cancel", None, True)
        await asyncio.to_thread(assistant_store.add_message, session, "assistant", result.get("response", "Request rejected."), None, True)
        return result
