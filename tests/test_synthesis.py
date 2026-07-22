from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_reach.errors import ResearchReachError
from research_reach.search import launch
from research_reach.synthesis import SYNTHESIS_SCHEMA, _prompt, synthesize
from tests.helpers import confirmed_brief, worker_result


class SynthesisTests(unittest.TestCase):
    def test_worker_schema_avoids_unsupported_unique_items(self) -> None:
        used_urls = SYNTHESIS_SCHEMA["properties"]["used_urls"]
        self.assertNotIn("uniqueItems", used_urls)

    def test_prompt_lists_exact_allowed_public_urls(self) -> None:
        evidence = worker_result()["evidence"]
        evidence.append({
            "url": "artifact://summary.json",
            "question_refs": ["q1"],
            "title": "Local summary",
            "text": "Aggregate",
            "evidence_kind": "metadata",
            "source_name": "Local",
            "retrieved_at": "2026-07-21",
        })
        with tempfile.TemporaryDirectory() as root:
            prompt = _prompt(confirmed_brief(Path(root)), evidence, [])
            self.assertIn('"https://example.com/source-1"', prompt)
            self.assertIn('"https://example.com/source-2"', prompt)
            allowed_section = prompt.split("Allowed public URLs:\n", 1)[1].split("\n\nEvidence:\n", 1)[0]
            self.assertNotIn("artifact://summary.json", allowed_section)

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
