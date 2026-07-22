from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_reach.common import load_json
from research_reach.contracts import load_evidence_jsonl
from research_reach.search import SEARCH_WORKER_SCHEMA, launch
from tests.helpers import confirmed_brief, worker_result


class SearchTests(unittest.TestCase):
    def test_worker_schema_requires_every_evidence_property(self) -> None:
        evidence = SEARCH_WORKER_SCHEMA["properties"]["evidence"]["items"]
        self.assertEqual(set(evidence["properties"]), set(evidence["required"]))

    def test_search_accepts_confirmed_local_artifact_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root)
            confirmed_brief(workdir)
            result = worker_result()
            result["evidence"][0]["url"] = "artifact://csv_token_summary.json"
            result["evidence"][0]["evidence_kind"] = "metadata"
            fixture = workdir / "search-output.json"
            fixture.write_text(json.dumps({"C1": result}), encoding="utf-8")

            status, data, errors = launch(workdir, None, str(fixture))
            self.assertEqual("ok", status)
            self.assertEqual([], errors)
            self.assertEqual(2, data["topics"][0]["evidence_count"])

    def test_search_writes_artifacts_and_public_handback_is_compact(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root)
            confirmed_brief(workdir)
            fixture = workdir / "search-output.json"
            fixture.write_text(json.dumps({"C1": worker_result()}), encoding="utf-8")

            status, data, errors = launch(workdir, None, str(fixture))
            self.assertEqual("ok", status)
            self.assertEqual([], errors)
            public = json.dumps(data)
            self.assertNotIn("Evidence for q1", public)
            self.assertNotIn("https://example.com", public)
            self.assertEqual(2, data["topics"][0]["evidence_count"])
            self.assertEqual(2, len(load_evidence_jsonl(workdir / "artifacts/search/C1/evidence.jsonl")))

    def test_rerun_deduplicates_and_new_brief_replaces_old_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root)
            brief = confirmed_brief(workdir)
            fixture = workdir / "search-output.json"
            fixture.write_text(json.dumps({"C1": worker_result()}), encoding="utf-8")
            launch(workdir, None, str(fixture))
            launch(workdir, None, str(fixture))
            self.assertEqual(2, len(load_evidence_jsonl(workdir / "artifacts/search/C1/evidence.jsonl")))

            brief["revision"] += 1
            brief["request"]["raw_input_full"] = "New confirmed request"
            from research_reach.contracts import brief_hash, write_brief
            brief["approval"]["content_sha256"] = brief_hash(brief)
            write_brief(workdir / "brief.json", brief)
            fixture.write_text(json.dumps({"C1": worker_result(questions=("q1",))}), encoding="utf-8")
            status, _, _ = launch(workdir, None, str(fixture))
            self.assertEqual("partial", status)
            self.assertEqual(1, len(load_evidence_jsonl(workdir / "artifacts/search/C1/evidence.jsonl")))
            manifest = load_json(workdir / "artifacts/search/C1/manifest.json")
            self.assertEqual(["q2"], manifest["uncovered_question_refs"])

    def test_rerun_does_not_launder_tampered_existing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root)
            confirmed_brief(workdir)
            fixture = workdir / "search-output.json"
            fixture.write_text(json.dumps({"C1": worker_result()}), encoding="utf-8")
            launch(workdir, None, str(fixture))
            evidence_path = workdir / "artifacts/search/C1/evidence.jsonl"
            evidence_path.write_text(evidence_path.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")

            launch(workdir, None, str(fixture))
            evidence = load_evidence_jsonl(evidence_path)
            self.assertEqual(2, len(evidence))
            self.assertTrue(all(item.get("schema_version") for item in evidence))


if __name__ == "__main__":
    unittest.main()
