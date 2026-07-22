from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from research_reach.contracts import load_brief
from research_reach.opening import confirm, draft, revise
from tests.helpers import topics


class OpeningTests(unittest.TestCase):
    def test_draft_revise_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            workdir = Path(root) / "work"
            workdir.mkdir()
            fixture = Path(root) / "opening-output.json"
            fixture.write_text(json.dumps({"topics": topics()}), encoding="utf-8")

            drafted = draft(workdir, {"raw_input_full": "Complete request"}, force=False, fixture=str(fixture))
            self.assertEqual("pending_confirmation", drafted["approval_status"])

            revised_topics = topics()
            revised_topics[0]["research_goal"] = "Revised goal"
            fixture.write_text(json.dumps({"topics": revised_topics}), encoding="utf-8")
            revised = revise(workdir, {"feedback": "Change the goal"}, fixture=str(fixture))
            self.assertEqual(2, revised["revision"])
            self.assertEqual("pending_confirmation", revised["approval_status"])

            confirmed = confirm(workdir, yes=True)
            self.assertEqual("confirmed", confirmed["approval_status"])
            self.assertEqual("Revised goal", load_brief(workdir / "brief.json", require_confirmed=True)["topics"][0]["research_goal"])


if __name__ == "__main__":
    unittest.main()
