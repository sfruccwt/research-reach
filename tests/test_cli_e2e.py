from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from research_reach import __version__
from tests.helpers import topics, worker_result


class CliFixtureE2ETests(unittest.TestCase):
    def test_package_version_matches_project_metadata(self) -> None:
        project = Path(__file__).resolve().parents[1] / "pyproject.toml"
        metadata = tomllib.loads(project.read_text(encoding="utf-8"))
        self.assertEqual(metadata["project"]["version"], __version__)

    def _run(self, module: str, *args: str) -> dict:
        environment = dict(os.environ)
        source = str(Path(__file__).resolve().parents[1] / "src")
        environment["PYTHONPATH"] = source + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
        completed = subprocess.run(
            [sys.executable, "-m", module, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
        self.assertIn(completed.returncode, {0, 6}, completed.stderr + completed.stdout)
        return json.loads(completed.stdout)

    def test_three_stage_fixture_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root) / "research"
            workdir.mkdir()
            request = Path(root) / "request.json"
            opening_fixture = Path(root) / "opening.json"
            search_fixture = Path(root) / "search.json"
            synthesis_fixture = Path(root) / "synthesis.json"
            request.write_text(json.dumps({"raw_input_full": "Traceable E2E request"}), encoding="utf-8")
            opening_fixture.write_text(json.dumps({"topics": topics()}), encoding="utf-8")
            search_fixture.write_text(json.dumps({"C1": worker_result()}), encoding="utf-8")
            synthesis_fixture.write_text(json.dumps({
                "report_markdown": "Verified [source](https://example.com/source-1).",
                "assessment": "complete",
                "used_urls": ["https://example.com/source-1"],
            }), encoding="utf-8")

            draft = self._run(
                "research_reach.opening",
                "draft", "--workdir", str(workdir), "--input", str(request), "--fixture", str(opening_fixture),
            )
            self.assertEqual("pending_confirmation", draft["data"]["approval_status"])
            self._run("research_reach.opening", "confirm", "--workdir", str(workdir), "--yes")
            search = self._run(
                "research_reach.search",
                "launch", "--workdir", str(workdir), "--fixture", str(search_fixture),
            )
            self.assertNotIn("https://example.com", json.dumps(search))
            synthesis = self._run(
                "research_reach.synthesis",
                "run", "--workdir", str(workdir), "--fixture", str(synthesis_fixture),
            )
            self.assertEqual("report.md", synthesis["data"]["report_ref"])
            self.assertTrue((workdir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
