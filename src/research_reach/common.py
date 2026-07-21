"""Small, stateless I/O helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from .errors import ResearchReachError, blocked, invalid


EXIT_CODES = {"ok": 0, "partial": 6, "blocked": 3, "failed": 4}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_json_input(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    if value == "-":
        raw = sys.stdin.read()
    else:
        path = Path(value)
        raw = path.read_text(encoding="utf-8-sig") if path.is_file() else value
    try:
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise invalid("input must be a UTF-8 JSON object, a JSON file, or '-'") from exc
    if not isinstance(parsed, dict):
        raise invalid("input JSON must be an object")
    return parsed


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise blocked(f"required file does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise invalid(f"file is not valid UTF-8 JSON: {path}") from exc


def workdir_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_path(path: Path) -> str:
    return str(path.resolve())


def emit(
    command: str,
    status: str,
    data: Mapping[str, Any],
    errors: list[dict[str, Any]] | None = None,
    *,
    exit_code: int | None = None,
) -> int:
    result: dict[str, Any] = {
        "schema_version": "research-reach.result/v2",
        "command": command,
        "status": status,
        "data": dict(data),
    }
    if errors:
        result["errors"] = errors
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return EXIT_CODES[status] if exit_code is None else exit_code


def fail(command: str, exc: Exception) -> int:
    if isinstance(exc, ResearchReachError):
        error = {"code": exc.code, "message": exc.message}
        return emit(command, exc.status, {}, [error], exit_code=exc.exit_code)
    error = {"code": "INTERNAL_ERROR", "message": "unexpected CLI failure"}
    return emit(command, "failed", {}, [error])


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid(f"{field} must be a non-empty string")
    return value.strip()


def string_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise invalid(f"{field} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise invalid(f"{field} must not be empty")
    return [item.strip() for item in value]
