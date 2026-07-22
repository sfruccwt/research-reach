"""Run isolated Codex model and Worker processes without persistent state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from .errors import ResearchReachError, blocked, invalid


def validate_output_schema(schema: Mapping[str, Any]) -> None:
    """Reject schema shapes known to be incompatible with Codex structured output."""

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            if "uniqueItems" in value:
                raise invalid(f"output schema uses unsupported uniqueItems at {path}")
            properties = value.get("properties")
            if value.get("type") == "object" and isinstance(properties, Mapping):
                required = value.get("required")
                property_names = set(properties)
                required_names = set(required) if isinstance(required, list) else set()
                if value.get("additionalProperties") is False and required_names != property_names:
                    missing = sorted(property_names - required_names)
                    extra = sorted(required_names - property_names)
                    detail = []
                    if missing:
                        detail.append(f"missing required keys: {', '.join(missing)}")
                    if extra:
                        detail.append(f"unknown required keys: {', '.join(extra)}")
                    raise invalid(f"strict output schema object at {path} must require every property ({'; '.join(detail)})")
            for key, child in value.items():
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(schema, "$")


def _resolve_codex_executable(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    configured = os.environ.get("RESEARCH_REACH_CODEX")
    if configured and Path(configured).is_file():
        return configured
    if os.name == "nt":
        bin_root = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"
        try:
            candidates = [path for path in bin_root.glob("*/codex.exe") if path.is_file()]
            if candidates:
                return str(max(candidates, key=lambda path: path.stat().st_mtime_ns))
        except OSError:
            pass
    return shutil.which("codex")


def _upstream_error_summary(stderr: str) -> str | None:
    for line in reversed(stderr.splitlines()):
        marker = "ERROR:"
        if marker not in line:
            continue
        candidate = line.split(marker, 1)[1].strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        error = payload.get("error") if isinstance(payload, Mapping) else None
        message = error.get("message") if isinstance(error, Mapping) else None
        if isinstance(message, str) and message.strip():
            return " ".join(message.split())[:1200]
    return None


def run_codex_json(
    *,
    prompt: str,
    schema: Mapping[str, Any],
    model: str,
    workdir: Path,
    worker_mode: str,
    network: bool,
    ignore_rules: bool = False,
    timeout_seconds: int = 900,
    executable: str | None = None,
) -> dict[str, Any]:
    validate_output_schema(schema)
    codex = _resolve_codex_executable(executable)
    if not codex:
        raise blocked("Codex CLI is not installed or no runnable executable was found")
    with tempfile.TemporaryDirectory(prefix="research-reach-") as temp_dir:
        root = Path(temp_dir)
        schema_path = root / "schema.json"
        output_path = root / "output.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        command = [
            codex,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
        ]
        if ignore_rules:
            command.append("--ignore-rules")
        command.extend([
            "--sandbox",
            "workspace-write" if network else "read-only",
            "-C",
            str(workdir),
            "-c",
            'approval_policy="never"',
        ])
        if network:
            command.extend(["--add-dir", str(workdir), "-c", "sandbox_workspace_write.network_access=true"])
            if os.name == "nt":
                command.extend(["-c", 'windows.sandbox="unelevated"'])
        command.extend([
            "--color",
            "never",
            "--model",
            model,
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
            "-",
        ])
        environment = dict(os.environ)
        environment["RESEARCH_REACH_WORKER_MODE"] = worker_mode
        environment["PYTHONIOENCODING"] = "utf-8"
        environment["PYTHONUTF8"] = "1"
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
                cwd=workdir,
                env=environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise ResearchReachError("TIMEOUT", "Codex Worker timed out", exit_code=4) from exc
        except OSError as exc:
            raise ResearchReachError("UPSTREAM_FAILED", "Codex Worker could not start", exit_code=4) from exc
        if completed.returncode != 0 or not output_path.is_file():
            message = f"Codex Worker failed (exit code {completed.returncode})"
            upstream_summary = _upstream_error_summary(completed.stderr)
            if upstream_summary:
                message += f": {upstream_summary}"
            raise ResearchReachError("UPSTREAM_FAILED", message, exit_code=4)
        try:
            value = json.loads(output_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchReachError("OUTPUT_PARSE_FAILED", "Codex Worker returned invalid JSON", exit_code=4) from exc
        if not isinstance(value, dict):
            raise ResearchReachError("OUTPUT_PARSE_FAILED", "Codex Worker output must be an object", exit_code=4)
        return value
