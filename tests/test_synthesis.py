from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_reach.errors import ResearchReachError
from research_reach.search import launch
from research_reach.synthesis import synthesize
from tests.helpers import confirmed_brief, worker_result


class SynthesisTests(unittest.TestCase):
    def _searched_workdir(self, root: str) -> Path:
        workdir = Path(root)
        confirmed_brief(workdir)
        search_fixture = workdir / "search-output.json"
        search_fixture.write_text(json.dumps({"C1": worker_result()}), encoding="utf-8")
        launch(workdir, None, str(search_fixture))
        return workdir

    def test_synthesis_writes_traceable_report(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = self._searched_workdir(root)
            fixture = workdir / "synthesis-output.json"
            fixture.write_text(json.dumps({
                "report_markdown": "The primary source supports the finding [Source](https://example.com/source-1).",
                "assessment": "complete",
                "used_urls": ["https://example.com/source-1"],
            }), encoding="utf-8")
            status, data, errors = synthesize(workdir, str(fixture))
            self.assertEqual("ok", status)
            self.assertEqual([], errors)
            report = (workdir / "report.md").read_text(encoding="utf-8")
            self.assertIn("Original request with all constraints", report)
            self.assertEqual(1, data["source_count"])

    def test_synthesis_rejects_url_outside_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = self._searched_workdir(root)
            fixture = workdir / "synthesis-output.json"
            fixture.write_text(json.dumps({
                "report_markdown": "Unsupported [link](https://invalid.example/).",
                "assessment": "complete",
                "used_urls": ["https://invalid.example/"],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ResearchReachError, "not present in evidence"):
                synthesize(workdir, str(fixture))

    def test_synthesis_rejects_tampered_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = self._searched_workdir(root)
            evidence = workdir / "artifacts/search/C1/evidence.jsonl"
            evidence.write_text(evidence.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
            fixture = workdir / "synthesis-output.json"
            fixture.write_text(json.dumps({
                "report_markdown": "No sources used.",
                "assessment": "insufficient",
                "used_urls": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ResearchReachError, "changed after collection"):
                synthesize(workdir, str(fixture))


if __name__ == "__main__":
    unittest.main()
