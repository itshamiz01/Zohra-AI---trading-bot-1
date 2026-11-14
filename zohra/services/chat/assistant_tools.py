"""Explicit, read-only backend access plus assistant-owned personal tasks."""
import json
import re
from datetime import datetime, timezone

from zohra.services.chat.assistant_store import assistant_store
from zohra.services.chat.assistant_search import search_web
from zohra.security.redaction import redact_secrets, redact_data


DOMAINS = ("system", "trading", "research", "memory", "learning", "agents")
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "list_capabilities", "description": "Read actual registered capabilities, availability, permissions and blockers. Never assume an unavailable tool can execute.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Search public web pages or recent news when asked to search/check online or for current information. Returns real snippets, links, publication dates when provided, and retrieval time; not full-page verification. Never include private backend/account/contact data or credentials in a query.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 400},
            "kind": {"type": "string", "enum": ["web", "news"]},
            "recency": {"type": "string", "enum": ["d", "w", "m", "y"]},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": ["query"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_backend_update",
        "description": "Read actual dashboard backend data. Trading uses timestamped account snapshots, not live orders. Report stale/unavailable data explicitly.",
        "parameters": {"type": "object", "properties": {
            "domain": {"type": "string", "enum": list(DOMAINS)},
            "query": {"type": "string", "description": "Optional text filter for memory."}}, "required": ["domain"]}}},
    {"type": "function", "function": {
        "name": "manage_tasks",
        "description": "List personal to-do items. Changes require the separate confirmed dashboard action bridge; this tool cannot create or complete tasks.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["list", "create", "complete"]},
            "title": {"type": "string"}, "task_id": {"type": "integer"}}, "required": ["action"]}}},
]


def get_backend_update(domain, query=""):
    from zohra.analytics import telemetry_provider, workspace_data
    sources = {
        "system": ("/api/v1/os/telemetry", telemetry_provider.get_system_telemetry),
        "trading": ("/api/v1/os/telemetry", telemetry_provider.get_trading_telemetry),
        "research": ("/api/v1/research", workspace_data.research_snapshot),
        "memory": ("/api/v1/memory", lambda: workspace_data.memory_snapshot(query[:200])),
        "learning": ("/api/v1/learning", workspace_data.learning_snapshot),
        "agents": ("/api/v1/agents", workspace_data.agent_snapshot),
    }
    if domain not in sources:
        return {"error": "Unsupported backend domain."}
    source, reader = sources[domain]
    return {"source": source, "observed_at": datetime.now(timezone.utc).isoformat(), "data": reader()}


def execute_tool(name, arguments, store=None):
    # Model output, user prompts, and speaker names cannot grant extra privileges.
    allowed = {"search_web": search_web, "get_backend_update": get_backend_update,
               "manage_tasks": (store or assistant_store).manage_tasks}
    if name == "list_capabilities":
        if arguments != {}:
            return {"error": "VALIDATION_ERROR: Capability inventory takes no arguments"}
        from zohra.services.tool_execution.catalog import capability_inventory
        return {"tools": capability_inventory()}
    if name not in allowed:
        return {"error": "PERMISSION_DENIED: This assistant connection cannot execute trading, payments, OS commands, or change engine settings. Use the existing verified controls."}
    if not isinstance(arguments, dict):
        return {"error": "Invalid tool arguments."}
    try:
        from zohra.services.tool_execution.catalog import check_capability, SearchInput, BackendInput
        tool_id = "web.search" if name == "search_web" else "tasks.list" if name == "manage_tasks" else "backend." + str(arguments.get("domain", ""))
        check_capability(tool_id)
        if name == "search_web":
            SearchInput.model_validate(arguments)
        elif name == "get_backend_update":
            BackendInput.model_validate({key: value for key, value in arguments.items() if key != "domain"})
    except (PermissionError, KeyError, ValueError, OSError) as error:
        return {"error": redact_secrets(f"{type(error).__name__}: {error}")}
    if name == "manage_tasks" and arguments.get("action", "list") != "list":
        return {"error": "CONFIRMATION_REQUIRED: Use the dashboard text action bridge. No task was changed."}
    if name == "manage_tasks" and (store is None or store is assistant_store):
        from zohra.services.chat.assistant_orchestrator import node_request
        return node_request({"session_id": "task-read-model", "operation": "tasks"})
    try:
        result = redact_data(allowed[name](**arguments))
        # Bound observations to avoid unbounded database records in model context.
        encoded = json.dumps(result, default=str, ensure_ascii=False)
        if len(encoded) > 24000:
            return {"source": result.get("source"), "status": "truncated", "summary": encoded[:23000]}
        return json.loads(encoded)
    except Exception as error:
        return {"error": redact_secrets(f"{type(error).__name__}: {error}. Backend data is unavailable; do not infer values.")}
