from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from research_reach.model_runner import run_codex_json


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


if __name__ == "__main__":
    unittest.main()
