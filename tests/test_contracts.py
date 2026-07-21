from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_reach.common import load_json
from research_reach.contracts import brief_hash, load_brief, new_brief, write_brief
from research_reach.errors import ResearchReachError
from tests.helpers import topics


class BriefContractTests(unittest.TestCase):
    def test_confirmation_is_bound_to_exact_content(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "brief.json"
            brief = new_brief("Complete request", topics())
            digest = brief_hash(brief)
            brief["approval"] = {"status": "confirmed", "content_sha256": digest, "confirmed_at": "now"}
            write_brief(path, brief)
            loaded = load_brief(path, require_confirmed=True)
            self.assertEqual(digest, brief_hash(loaded))

            value = json.loads(path.read_text(encoding="utf-8"))
            value["topics"][0]["research_goal"] = "Changed after confirmation"
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ResearchReachError, "changed after confirmation"):
                load_brief(path, require_confirmed=True)

    def test_duplicate_question_refs_are_rejected(self) -> None:
        value = topics()
        value[0]["search_plan"]["questions"].append({"question_ref": "q1", "question": "Duplicate"})
        with self.assertRaisesRegex(ResearchReachError, "duplicate question_ref"):
            new_brief("request", value)

    def test_missing_json_is_a_public_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ResearchReachError, "required file does not exist") as raised:
                load_json(Path(root) / "missing.json")
            self.assertEqual("blocked", raised.exception.status)


if __name__ == "__main__":
    unittest.main()
