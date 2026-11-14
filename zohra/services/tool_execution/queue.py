from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List

from zohra.services.tool_execution.engine import ToolExecutionEngine, ToolExecutionResult
from zohra.services.tool_execution.models import ToolCall


@dataclass
class DeadLetter:
    call: ToolCall
    result: ToolExecutionResult
    attempts: int


class ToolTaskQueue:
    """Small local retry queue mirroring the V2 task-queue semantics."""

    def __init__(self, engine: ToolExecutionEngine, max_retries: int = 3):
        self.engine = engine
        self.max_retries = max_retries
        self.dead_letters: List[DeadLetter] = []

    async def submit(self, call: ToolCall) -> ToolExecutionResult:
        last_result = None
        for attempt in range(1, self.max_retries + 2):
            last_result = await self.engine.execute(call)
            # Never replay approval previews or uncertain state-changing execution.
            if last_result.status in {"completed", "requires_confirmation", "rejected"}:
                return last_result
            definition = self.engine.registry.definition(call.tool_id)
            if not definition or definition.risk_level > 0 or last_result.error_code in {"PERMISSION_DENIED", "VALIDATION_ERROR", "UNKNOWN_TOOL"}:
                return last_result
            if attempt <= self.max_retries:
                await asyncio.sleep(0.25 * attempt)

        self.dead_letters.append(DeadLetter(call=call, result=last_result, attempts=self.max_retries + 1))
        return last_result
