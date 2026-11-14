"""Server-owned capability contracts, shared by the existing execution engine."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from pydantic import BaseModel, ConfigDict


class CapabilityState(str, Enum):
    AVAILABLE = "Available"
    PERMISSION_REQUIRED = "Permission Required"
    DEPENDENCY_MISSING = "Dependency Missing"
    UNSUPPORTED = "Unsupported"
    TEMPORARILY_UNAVAILABLE = "Temporarily Unavailable"
    EXECUTION_FAILED = "Execution Failed"


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ObjectOutput(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    category: str
    platform: str = "Shared"
    input_model: type[BaseModel] = EmptyInput
    output_model: type[BaseModel] = ObjectOutput
    permissions: tuple[str, ...] = ()
    risk_level: int = 0
    timeout_sec: float = 10.0
    confirmation_required: bool = False
    reversible: bool = True
    expected_duration_ms: int = 100
    dependencies: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ("VALIDATION_ERROR", "PERMISSION_DENIED", "TOOL_UNAVAILABLE", "TIMEOUT", "VERIFICATION_FAILED")
    availability: Callable = field(default=lambda: (CapabilityState.AVAILABLE, "Ready"), repr=False)
    # A trusted bridge can only propose an action; it cannot bypass its own gate.
    confirmation_bridge: bool = False
    private_output: bool = False
    verification: Callable | None = field(default=None, repr=False)

    def __post_init__(self):
        if not 0 <= self.risk_level <= 4 or not 0 < self.timeout_sec <= 120:
            raise ValueError("Invalid server-owned tool policy")
        if self.risk_level > 0 and not self.confirmation_required:
            raise ValueError("State-changing tools require confirmation in this installation")

    def describe(self):
        state, reason = self.availability()
        return {
            "name": self.name, "description": self.description, "category": self.category,
            "platform": self.platform, "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(), "permissions": list(self.permissions),
            "risk_level": self.risk_level, "timeout_sec": self.timeout_sec,
            "confirmation_required": self.confirmation_required, "reversible": self.reversible,
            "private_output": self.private_output,
            "expected_duration_ms": self.expected_duration_ms, "dependencies": list(self.dependencies),
            "error_codes": list(self.error_codes), "availability": state.value, "reason": reason,
        }


class ToolRegistry:
    def __init__(self):
        self._handlers = {}
        self._dry_run_handlers = {}
        self._definitions = {}

    def register(self, tool_id, handler=None, dry_run_handler=None, *, definition=None):
        if definition is not None and definition.name != tool_id:
            raise ValueError("Tool ID and contract name must match")
        if tool_id in self._handlers and self._handlers[tool_id] is not handler:
            raise ValueError(f"Tool '{tool_id}' is already registered")
        self._handlers[tool_id] = handler
        if dry_run_handler:
            self._dry_run_handlers[tool_id] = dry_run_handler
        if definition:
            self._definitions[tool_id] = definition

    def get(self, tool_id):
        if tool_id not in self._handlers:
            raise KeyError(f"Tool '{tool_id}' is not registered")
        return self._handlers[tool_id]

    def get_dry_run(self, tool_id):
        return self._dry_run_handlers.get(tool_id)

    def definition(self, tool_id):
        if tool_id not in self._handlers:
            raise KeyError(f"Tool '{tool_id}' is not registered")
        return self._definitions.get(tool_id)

    def describe(self):
        records = []
        for name in sorted(self._handlers):
            definition = self._definitions.get(name)
            records.append(definition.describe() if definition else {
                "name": name, "category": "Legacy Windows", "platform": "Windows",
                "availability": CapabilityState.UNSUPPORTED.value,
                "reason": "Unverified legacy implementation; no validated contract. Execution is blocked.",
                "risk_level": 3, "confirmation_required": True,
            })
        return records
