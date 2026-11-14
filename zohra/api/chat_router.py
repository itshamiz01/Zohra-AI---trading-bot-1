"""Compatibility endpoints using the same confirmed Node action bridge."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from zohra.api.assistant_router import Message, local_only
from zohra.services.chat.assistant_orchestrator import text_request

router = APIRouter(prefix="/api/v1/chat", tags=["Chat Command Center"])


@router.post("/message")
async def handle_chat_message(req: Message, request: Request):
    local_only(request)
    result = await text_request(req.session_id, req.message)
    return {**result, "session_id": req.session_id, "intent": result.get("lane"),
            "timestamp": datetime.now(timezone.utc).isoformat(), "raw_data": result.get("data")}


@router.post("/stream")
async def handle_chat_stream(req: Message, request: Request):
    local_only(request)

    async def events():
        result = await text_request(req.session_id, req.message)
        yield f"data: {json.dumps({'type': 'result', **result})}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'content': result.get('response', '')})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
