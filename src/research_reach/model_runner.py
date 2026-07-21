"""Run isolated Codex model and Worker processes without persistent state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from .errors import ResearchReachError, blocked


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
    codex = executable or shutil.which("codex")
    if not codex:
        raise blocked("Codex CLI is not installed or not on PATH")
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
            raise ResearchReachError("UPSTREAM_FAILED", "Codex Worker failed", exit_code=4)
        try:
            value = json.loads(output_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchReachError("OUTPUT_PARSE_FAILED", "Codex Worker returned invalid JSON", exit_code=4) from exc
        if not isinstance(value, dict):
            raise ResearchReachError("OUTPUT_PARSE_FAILED", "Codex Worker output must be an object", exit_code=4)
        return value
