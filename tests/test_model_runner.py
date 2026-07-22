from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research_reach.errors import ResearchReachError
from research_reach.model_runner import _resolve_codex_executable, run_codex_json, validate_output_schema
from research_reach.opening import OPENING_SCHEMA
from research_reach.search import SEARCH_WORKER_SCHEMA
from research_reach.synthesis import SYNTHESIS_SCHEMA


class ModelRunnerTests(unittest.TestCase):
    def _fake_run(self, commands: list[list[str]]):
        def run(command, **kwargs):
            commands.append(command)
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text(json.dumps({"ok": True}), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")
        return run

    def test_network_flag_is_only_added_for_search_worker(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            commands: list[list[str]] = []
            with patch("research_reach.model_runner.subprocess.run", side_effect=self._fake_run(commands)):
                run_codex_json(
                    prompt="test",
                    schema={"type": "object"},
                    model="test-model",
                    workdir=Path(root),
                    worker_mode="synthesis",
                    network=False,
                    ignore_rules=True,
                    executable="codex",
                )
                run_codex_json(
                    prompt="test",
                    schema={"type": "object"},
                    model="test-model",
                    workdir=Path(root),
                    worker_mode="search",
                    network=True,
                    executable="codex",
                )
            self.assertNotIn("sandbox_workspace_write.network_access=true", commands[0])
            self.assertIn("sandbox_workspace_write.network_access=true", commands[1])
            self.assertIn("--ignore-rules", commands[0])
            self.assertNotIn("--ignore-rules", commands[1])

    def test_all_stage_schemas_pass_strict_preflight(self) -> None:
        for schema in (OPENING_SCHEMA, SEARCH_WORKER_SCHEMA, SYNTHESIS_SCHEMA):
            with self.subTest(schema=schema):
                validate_output_schema(schema)

    def test_strict_schema_requires_every_property_before_worker_launch(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["present"],
            "properties": {"present": {"type": "string"}, "missing": {"type": ["string", "null"]}},
        }
        with tempfile.TemporaryDirectory() as root:
            with patch("research_reach.model_runner.subprocess.run") as run:
                with self.assertRaisesRegex(ResearchReachError, "missing required keys: missing"):
                    run_codex_json(
                        prompt="test",
                        schema=schema,
                        model="test-model",
                        workdir=Path(root),
                        worker_mode="search",
                        network=True,
                        executable="codex",
                    )
                run.assert_not_called()

    def test_schema_rejects_unsupported_unique_items_before_worker_launch(self) -> None:
        schema = {"type": "array", "uniqueItems": True, "items": {"type": "string"}}
        with tempfile.TemporaryDirectory() as root:
            with patch("research_reach.model_runner.subprocess.run") as run:
                with self.assertRaisesRegex(ResearchReachError, "unsupported uniqueItems"):
                    run_codex_json(
                        prompt="test",
                        schema=schema,
                        model="test-model",
                        workdir=Path(root),
                        worker_mode="synthesis",
                        network=False,
                        executable="codex",
                    )
                run.assert_not_called()

    def test_worker_failure_exposes_only_structured_upstream_error(self) -> None:
        stderr = (
            "private prompt that must stay hidden\n"
            'ERROR: {"error":{"message":"Invalid schema for response_format test"}}\n'
            "private evidence that must stay hidden\n"
        )
        completed = subprocess.CompletedProcess(["codex"], 1, "", stderr)
        with tempfile.TemporaryDirectory() as root:
            with patch("research_reach.model_runner.subprocess.run", return_value=completed):
                with self.assertRaises(ResearchReachError) as raised:
                    run_codex_json(
                        prompt="secret",
                        schema={"type": "object"},
                        model="test-model",
                        workdir=Path(root),
                        worker_mode="search",
                        network=True,
                        executable="codex",
                    )
        self.assertIn("Invalid schema for response_format test", raised.exception.message)
        self.assertNotIn("private prompt", raised.exception.message)
        self.assertNotIn("private evidence", raised.exception.message)

    def test_valid_configured_codex_path_precedes_path_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            executable = Path(root) / "codex.exe"
            executable.write_bytes(b"")
            with patch.dict("os.environ", {"RESEARCH_REACH_CODEX": str(executable)}):
                with patch("research_reach.model_runner.shutil.which", return_value="fallback-codex"):
                    self.assertEqual(str(executable), _resolve_codex_executable(None))

    def test_stale_configured_codex_path_is_ignored(self) -> None:
        stale = str(Path(tempfile.gettempdir()) / "missing-research-reach-codex.exe")
        with patch.dict("os.environ", {"RESEARCH_REACH_CODEX": stale}):
            with patch("research_reach.model_runner.shutil.which", return_value="fallback-codex"):
                resolved = _resolve_codex_executable(None)
        self.assertNotEqual(stale, resolved)
        self.assertTrue(resolved)


if __name__ == "__main__":
    unittest.main()
