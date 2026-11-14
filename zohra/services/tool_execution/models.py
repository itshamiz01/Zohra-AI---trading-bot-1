from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict
from pydantic import BaseModel

from zohra.security.permissions import PermissionTier


@dataclass
class ToolCall:
    tool_id: str
    action: str
    params: Dict[str, Any]
    requesting_agent: str
    permission_tier_required: PermissionTier
    reversible: bool
    dry_run_available: bool = False
    tool_call_id: str = field(default_factory=lambda: f"tool_{uuid.uuid4().hex[:12]}")
    timeout_sec: float = 10.0

    @property
    def capability(self) -> str:
        return self.tool_id.split(".", 1)[0]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_id": self.tool_id,
            "action": self.action,
            "params": self.params,
            "requesting_agent": self.requesting_agent,
            "permission_tier_required": int(self.permission_tier_required),
            "reversible": self.reversible,
            "dry_run_available": self.dry_run_available,
            "timeout_sec": self.timeout_sec,
        }


@dataclass
class WindowsToolCall(ToolCall):
    windows_api_used: str = ""
    requires_elevation: bool = False
    affects_unnamed_files: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "windows_api_used": self.windows_api_used,
            "requires_elevation": self.requires_elevation,
            "affects_unnamed_files": self.affects_unnamed_files,
        })
        return d


class ShredResult(BaseModel):
    path: str
    passes_completed: int
    confirmed_deleted: bool

