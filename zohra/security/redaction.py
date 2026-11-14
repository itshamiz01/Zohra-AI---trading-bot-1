"""Credential redaction without loading conversation providers or history storage."""
import re


def redact_secrets(text):
    text = re.sub(r"(?:sk-|gsk_|AIza)[A-Za-z0-9_-]{20,}", "[secret redacted]", text)
    return re.sub(r"\b(?:password|api_key|secret)\s*[:=]\s*\S+", "[secret redacted]", text, flags=re.I)


def redact_data(value):
    if isinstance(value, dict):
        return {key: "[secret redacted]" if re.search(
            r"(?:password|api[_-]?key|secret|token|authorization|private[_-]?key)", str(key), re.I)
            else redact_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    return redact_secrets(value) if isinstance(value, str) else value
