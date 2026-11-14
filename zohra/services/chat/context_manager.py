from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _normalize_role(role: str) -> str:
    role = (role or "user").lower()
    if role in {"assistant", "bot", "model"}:
        return "assistant"
    if role in {"tool", "function"}:
        return "tool"
    return "user"


def _section_block(title: str, content: str) -> str:
    content = content.strip()
    if not content:
        return ""
    return f"[{title}]\n{content}"


@dataclass(frozen=True)
class ContextSection:
    name: str
    source: str
    content: str


@dataclass(frozen=True)
class ContextAssembly:
    system_prompt: str
    permission_summary: str
    retrieved_memory: str
    recent_turns: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    user_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def sections(self) -> List[ContextSection]:
        sections: List[ContextSection] = [
            ContextSection("system_prompt", "template", self.system_prompt.strip()),
            ContextSection("permission_summary", "policy", self.permission_summary.strip()),
            ContextSection("retrieved_memory", "memory", self.retrieved_memory.strip()),
            ContextSection(
                "recent_turns",
                "session",
                "\n".join(
                    f"{turn.get('role', 'user')}: {turn.get('content', '').strip()}"
                    for turn in self.recent_turns
                    if turn.get("content")
                ).strip(),
            ),
            ContextSection(
                "tool_results",
                "tools",
                "\n".join(
                    f"{item.get('name', 'tool')}: {_stringify(item.get('result', item))}"
                    for item in self.tool_results
                    if item
                ).strip(),
            ),
            ContextSection("user_message", "input", self.user_message.strip()),
        ]
        return [section for section in sections if section.content]

    def render_text(self) -> str:
        return "\n\n".join(_section_block(section.name, section.content) for section in self.sections())

    def inspection_record(self) -> Dict[str, Any]:
        sections = [
            {
                "name": section.name,
                "source": section.source,
                "content": section.content,
            }
            for section in self.sections()
        ]
        canonical = json.dumps(sections, sort_keys=True, ensure_ascii=False, default=str)
        signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "sections": sections,
            "signature": signature,
            "metadata": dict(self.metadata),
        }

    def to_openai_messages(self) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []

        if self.system_prompt.strip():
            messages.append({"role": "system", "content": self.system_prompt.strip()})

        if self.permission_summary.strip():
            messages.append({
                "role": "system",
                "content": _section_block("permission_summary", self.permission_summary),
            })

        if self.retrieved_memory.strip():
            messages.append({
                "role": "system",
                "content": _section_block("retrieved_memory", self.retrieved_memory),
            })

        for turn in self.recent_turns:
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            messages.append({
                "role": _normalize_role(turn.get("role", "user")),
                "content": content,
            })

        if self.tool_results:
            messages.append({
                "role": "system",
                "content": _section_block(
                    "tool_results",
                    "\n".join(
                        f"{item.get('name', 'tool')}: {_stringify(item.get('result', item))}"
                        for item in self.tool_results
                        if item
                    ),
                ),
            })

        if self.user_message.strip():
            messages.append({"role": "user", "content": self.user_message.strip()})

        return messages

    def to_gemini_messages(self) -> List[Dict[str, Any]]:
        sections = []
        if self.system_prompt.strip():
            sections.append(self.system_prompt.strip())
        if self.permission_summary.strip():
            sections.append(_section_block("permission_summary", self.permission_summary))
        if self.retrieved_memory.strip():
            sections.append(_section_block("retrieved_memory", self.retrieved_memory))
        if self.tool_results:
            sections.append(
                _section_block(
                    "tool_results",
                    "\n".join(
                        f"{item.get('name', 'tool')}: {_stringify(item.get('result', item))}"
                        for item in self.tool_results
                        if item
                    ),
                )
            )

        messages: List[Dict[str, Any]] = []
        if sections:
            messages.append({
                "role": "user",
                "parts": [{"text": "\n\n".join(section for section in sections if section)}],
            })

        for turn in self.recent_turns:
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            messages.append({
                "role": "model" if _normalize_role(turn.get("role", "user")) == "assistant" else "user",
                "parts": [{"text": content}],
            })

        if self.user_message.strip():
            messages.append({
                "role": "user",
                "parts": [{"text": self.user_message.strip()}],
            })

        return messages


class ContextManager:
    """Builds deterministic, inspectable context assemblies."""

    def build(
        self,
        *,
        system_prompt: str,
        permission_summary: str,
        retrieved_memory: str,
        recent_turns: Optional[Iterable[Dict[str, Any]]] = None,
        tool_results: Optional[Iterable[Dict[str, Any]]] = None,
        user_message: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextAssembly:
        normalized_turns: List[Dict[str, Any]] = []
        for turn in recent_turns or []:
            if not turn:
                continue
            content = str(turn.get("content", "")).strip()
            if not content:
                continue
            normalized_turns.append(
                {
                    "role": _normalize_role(turn.get("role", "user")),
                    "content": content,
                    "intent": turn.get("intent"),
                    "parameters": turn.get("parameters"),
                }
            )

        normalized_tools: List[Dict[str, Any]] = []
        for item in tool_results or []:
            if not item:
                continue
            normalized_tools.append(dict(item))

        ordered_metadata = dict(metadata or {})
        ordered_metadata.setdefault("section_order", [
            "system_prompt",
            "permission_summary",
            "retrieved_memory",
            "recent_turns",
            "tool_results",
            "user_message",
        ])

        return ContextAssembly(
            system_prompt=system_prompt,
            permission_summary=permission_summary,
            retrieved_memory=retrieved_memory,
            recent_turns=normalized_turns,
            tool_results=normalized_tools,
            user_message=user_message,
            metadata=ordered_metadata,
        )

