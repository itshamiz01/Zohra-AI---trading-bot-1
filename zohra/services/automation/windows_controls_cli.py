"""Fixed JSON-stdin bridge. No shell strings, arbitrary scripts or elevation."""
import json
import sys

from zohra.services.automation.windows_controls import NativeRequest, prepare_control, execute_control


def main():
    try:
        raw = sys.stdin.read(20001)
        if len(raw) > 20000:
            raise ValueError("Native request exceeds 20KB")
        request = NativeRequest.model_validate(json.loads(raw))
        if request.operation == "prepare":
            result = prepare_control(request.action, request.args)
        else:
            result = execute_control(request.action, request.args, request.approval.model_dump() if request.approval else None)
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=True))
    except Exception as error:
        print(json.dumps({"ok": False, "error": {"code": getattr(error, "code", type(error).__name__), "message": str(error)}}, ensure_ascii=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
