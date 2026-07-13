"""CLI entry point for the stable ATO bridge."""

import json
import sys
from typing import Any

from .commands import dispatch
from .protocol import BridgeCommandError, failure, success


def _read_payload() -> dict[str, Any]:
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BridgeCommandError("INVALID_REQUEST", "Request must be UTF-8 JSON") from exc
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BridgeCommandError("INVALID_REQUEST", f"Invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise BridgeCommandError("INVALID_REQUEST", "Request payload must be a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    try:
        response = success(dispatch(command, _read_payload()))
        exit_code = 0
    except BridgeCommandError as exc:
        response = failure(exc)
        exit_code = 1
    except Exception as exc:
        response = failure(BridgeCommandError("INTERNAL_ERROR", str(exc)))
        exit_code = 1
    sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
