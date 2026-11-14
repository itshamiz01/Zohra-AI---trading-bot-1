"""Explicit visual-only dismissal commands; never route these to the agent."""
import re


def portrait_command(text: str) -> str | None:
    normalized = re.sub(r"[^a-z\u0900-\u097f\s]", " ", (text or "").lower())
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"^(?:okay|ok|zohra|zohara)\s+", "", normalized)
    return "hide" if normalized in {"over", "\u0913\u0935\u0930", "now you can go"} else None
