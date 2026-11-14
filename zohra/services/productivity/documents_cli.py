"""Fixed JSON stdin adapter; callers cannot select scripts or bypass approval."""
import json
import sys

from pydantic import BaseModel, ConfigDict
from typing import Literal
from zohra.services.productivity.documents import DocumentInput, Approval, prepare_document, execute_document
from zohra.security.redaction import redact_secrets


class Request(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    operation: Literal["prepare", "execute"]
    args: DocumentInput
    approval: Approval | None = None


def main():
    try:
        raw = sys.stdin.buffer.read(610001)
        if len(raw) > 610000:
            raise ValueError("Encoded document request exceeds 610 KB")
        request = Request.model_validate_json(raw)
        result = prepare_document(request.args.model_dump()) if request.operation == "prepare" else execute_document(
            request.args.model_dump(), request.approval.model_dump() if request.approval else None)
        response = {"ok": True, "result": result}
    except Exception as error:
        response = {"ok": False, "error": {"code": getattr(error, "code", type(error).__name__), "message": redact_secrets(str(error))}}
    sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
